import arxiv
from openai import OpenAI
import json
import os
import datetime
import time
import html
import re
import urllib.request
from dateutil import tz
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()

# ── Configuration (all overridable via environment variables) ────────────

def _parse_list(env_value: str, default: str) -> list[str]:
    """Parse a comma-separated env string; falls back to *default* when unset or empty."""
    raw = os.getenv(env_value)
    if not raw or not raw.strip():
        raw = default
    return [s.strip() for s in raw.split(",") if s.strip()]


def _parse_int(env_value: str, default: int) -> int:
    """Parse an integer env var; falls back to *default* when unset or empty."""
    raw = os.getenv(env_value)
    if not raw or not raw.strip():
        return default
    return int(raw)


KEYWORDS = _parse_list(
    "ARXIV_KEYWORDS",
    "3D Reconstruction,SLAM,Visual SLAM,VIO,Visual Inertial Odometry,"
    "Visual Odometry,Camera Localization,Visual Localization,"
    "Structure from Motion,Pose Estimation,NeRF,Gaussian Splatting",
)
CATEGORIES = _parse_list("ARXIV_CATEGORIES", "cs.CV,cs.AI")
MAX_DAYS = _parse_int("ARXIV_MAX_DAYS", 7)
MAX_PAPERS_PER_RUN = _parse_int("ARXIV_MAX_PAPERS_PER_RUN", 40)
FETCH_DAYS = _parse_int("ARXIV_FETCH_DAYS", 3)
BACKFILL_LIMIT = _parse_int("ARXIV_BACKFILL_LIMIT", 20)
MODEL_ID = os.getenv("DEEPSEEK_MODEL") or "deepseek-v4-flash"

DATA_FILE = "docs/data.json"
ARXIV_USER_AGENT = os.getenv("ARXIV_USER_AGENT") or "daily-arxiv/1.0"

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

def format_arxiv_datetime(dt: datetime.datetime) -> str:
    """Format a UTC datetime for arxiv submittedDate range queries."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz.tzutc())
    return dt.astimezone(tz.tzutc()).strftime("%Y%m%d%H%M")

def build_arxiv_search_query(lower_bound: datetime.datetime, upper_bound: datetime.datetime) -> str:
    keyword_query = " OR ".join([f'all:"{k}"' for k in KEYWORDS])
    category_query = " OR ".join([f"cat:{c}" for c in CATEGORIES])
    date_query = (
        f"submittedDate:[{format_arxiv_datetime(lower_bound)} "
        f"TO {format_arxiv_datetime(upper_bound)}]"
    )
    return f"({keyword_query}) AND ({category_query}) AND {date_query}"

def is_retryable_arxiv_error(error: Exception) -> bool:
    err_str = str(error)
    return any(code in err_str for code in ("429", "500", "503")) or "rate" in err_str.lower()

def clean_html_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    return " ".join(html.unescape(text).split())

def matches_keywords(title: str, abstract: str) -> bool:
    haystack = f"{title} {abstract}".lower()
    return any(keyword.lower() in haystack for keyword in KEYWORDS)

def parse_abs_page(arxiv_id: str, page_html: str) -> Dict:
    title_match = re.search(r'<h1 class="title[^"]*">\s*<span class="descriptor">Title:</span>(.*?)</h1>', page_html, re.S)
    abstract_match = re.search(r'<blockquote class="abstract[^"]*">\s*<span class="descriptor">Abstract:</span>(.*?)</blockquote>', page_html, re.S)
    date_match = re.search(r"\[Submitted on (\d{1,2} \w+ \d{4})", page_html)
    subject_match = re.search(r"\((cs\.[A-Z]+)\)", page_html)
    authors = re.findall(r'<meta name="citation_author" content="([^"]+)"', page_html)

    if not title_match or not abstract_match or not date_match:
        raise ValueError(f"Could not parse arxiv abs page for {arxiv_id}")

    submitted = datetime.datetime.strptime(date_match.group(1), "%d %b %Y").date()
    category = subject_match.group(1) if subject_match and subject_match.group(1) in CATEGORIES else "Unknown"

    return {
        "id": f"https://arxiv.org/abs/{arxiv_id}",
        "title": clean_html_text(title_match.group(1)),
        "authors": [html.unescape(author) for author in authors],
        "abstract": clean_html_text(abstract_match.group(1)),
        "link": f"https://arxiv.org/abs/{arxiv_id}",
        "published": submitted.strftime("%Y-%m-%d"),
        "category": category,
    }

def parse_list_page_candidates(page_html: str) -> List[Dict]:
    candidates = []
    current_date = None
    parts = re.split(r"(<h3>.*?</h3>)", page_html, flags=re.S)
    for part in parts:
        date_match = re.search(r"<h3>\w+,\s+(\d{1,2} \w+ \d{4})", part)
        if date_match:
            current_date = datetime.datetime.strptime(date_match.group(1), "%d %b %Y").date().strftime("%Y-%m-%d")
            continue
        if not current_date:
            continue

        for item_match in re.finditer(r'<dt>.*?id="([^"]+)".*?</dt>\s*<dd>.*?<div class=\'list-title mathjax\'><span class=\'descriptor\'>Title:</span>(.*?)</div>', part, re.S):
            candidates.append({
                "id": item_match.group(1).split("v")[0],
                "title": clean_html_text(item_match.group(2)),
                "published": current_date,
            })
    return candidates

def fetch_url(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": ARXIV_USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")

def get_papers_from_html_fallback() -> List[Dict]:
    print("Falling back to arxiv.org HTML pages because export.arxiv.org is unavailable.")
    windows = get_target_windows()
    lower_bound = min(window[0] for window in windows).date()
    upper_bound = max(window[1] for window in windows).date()
    candidates = []
    seen_ids = set()

    for category in CATEGORIES:
        url = f"https://arxiv.org/list/{category}/pastweek?skip=0&show=500"
        try:
            page_html = fetch_url(url)
        except Exception as e:
            print(f"Error fetching HTML list page {url}: {e}")
            continue

        for candidate in parse_list_page_candidates(page_html):
            arxiv_id = candidate["id"]
            if arxiv_id in seen_ids:
                continue
            published = datetime.datetime.strptime(candidate["published"], "%Y-%m-%d").date()
            if not (lower_bound <= published < upper_bound):
                continue
            if not matches_keywords(candidate["title"], ""):
                continue
            seen_ids.add(arxiv_id)
            candidates.append(candidate)

    print(f"HTML fallback found {len(candidates)} title-matched candidate ids.")
    papers = []
    for candidate in candidates:
        if len(papers) >= MAX_PAPERS_PER_RUN:
            break
        arxiv_id = candidate["id"]
        try:
            paper = parse_abs_page(arxiv_id, fetch_url(f"https://arxiv.org/abs/{arxiv_id}"))
        except Exception as e:
            print(f"Error parsing HTML abs page for {arxiv_id}: {e}")
            continue

        if paper["category"] not in CATEGORIES:
            continue
        papers.append(paper)
        time.sleep(1)

    print(f"HTML fallback matched {len(papers)} papers.")
    return papers

def get_target_windows(now_utc: datetime.datetime | None = None) -> List[tuple[datetime.datetime, datetime.datetime]]:
    """Return daily UTC windows ending at today's midnight."""
    if now_utc is None:
        now_utc = datetime.datetime.now(tz.tzutc())
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=tz.tzutc())
    today_start = now_utc.astimezone(tz.tzutc()).replace(hour=0, minute=0, second=0, microsecond=0)
    fetch_days = max(1, FETCH_DAYS)
    return [
        (today_start - datetime.timedelta(days=i), today_start - datetime.timedelta(days=i - 1))
        for i in range(fetch_days, 0, -1)
    ]

def get_papers() -> List[Dict]:
    """Fetch arxiv papers published in recent UTC day windows.

    The submittedDate range is pushed into the arxiv query. Fetching the
    newest MAX_PAPERS_PER_RUN first and filtering locally can miss the
    intended day when many newer papers already exist. Multiple day windows
    make the daily job resilient to missed runs and weekend/no-release days.
    """
    import random

    results = []
    seen_ids = set()

    max_retries = 1
    base_delay = 10

    for lower_bound, upper_bound in get_target_windows():
        print(f"Searching arxiv for papers published in [{lower_bound.isoformat()} , {upper_bound.isoformat()})")
        search_query = build_arxiv_search_query(lower_bound, upper_bound)
        print(f"Arxiv search query: {search_query}")

        for attempt in range(max_retries):
            arxiv_client = arxiv.Client(
                page_size=50,
                delay_seconds=5,
                num_retries=0
            )

            search = arxiv.Search(
                query=search_query,
                max_results=MAX_PAPERS_PER_RUN,
                sort_by=arxiv.SortCriterion.SubmittedDate
            )

            try:
                for result in arxiv_client.results(search):
                    published = result.published
                    if published >= upper_bound:
                        continue
                    if published < lower_bound:
                        continue
                    if result.entry_id in seen_ids:
                        continue
                    seen_ids.add(result.entry_id)

                    paper_cats = [c for c in result.categories if c in CATEGORIES]
                    category = paper_cats[0] if paper_cats else "Unknown"
                    results.append({
                        "id": result.entry_id,
                        "title": result.title,
                        "authors": [a.name for a in result.authors],
                        "abstract": result.summary,
                        "link": result.entry_id,
                        "published": published.strftime("%Y-%m-%d"),
                        "category": category
                    })
                break
            except Exception as e:
                if is_retryable_arxiv_error(e):
                    if attempt + 1 < max_retries:
                        jitter = random.uniform(0.5, 1.5)
                        wait_time = base_delay * (2 ** attempt) * jitter
                        print(f"Arxiv 限流/不可用，等待 {wait_time:.0f}s（第 {attempt + 1}/{max_retries} 次重试）...")
                        time.sleep(wait_time)
                    else:
                        print("export.arxiv.org is rate limited or unavailable; switching to HTML fallback.")
                else:
                    print(f"Error fetching from Arxiv: {e}")
                    break
        else:
            print(f"Arxiv 请求失败，已重试 {max_retries} 次。")

    if not results:
        results = get_papers_from_html_fallback()

    return results

def backfill_categories(data: List[Dict]) -> List[Dict]:
    """Batch-fetch category metadata for papers that lack it."""
    stale = [p for p in data if p.get("category", "Unknown") == "Unknown"]
    if not stale:
        return data

    print(f"Backfilling categories for {len(stale)} existing papers...")
    ids = [p["id"].split("/abs/")[-1] for p in stale]

    import random

    id_to_cat = {}
    for attempt in range(3):
        ac = arxiv.Client(page_size=len(ids), delay_seconds=5, num_retries=0)
        try:
            for result in ac.results(arxiv.Search(id_list=ids)):
                paper_cats = [c for c in result.categories if c in CATEGORIES]
                id_to_cat[result.entry_id] = paper_cats[0] if paper_cats else "Unknown"
            break
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "503" in err_str:
                wait = 10 * (2 ** attempt) * random.uniform(0.5, 1.5)
                print(f"Category backfill rate limited, waiting {wait:.0f}s...")
                time.sleep(wait)
            else:
                print(f"Error backfilling categories: {e}")
                return data
    else:
        print(f"Category backfill failed after {3} attempts.")

    for p in data:
        if p.get("category", "Unknown") == "Unknown":
            p["category"] = id_to_cat.get(p["id"], "Unknown")

    cv = sum(1 for p in data if p.get("category") == "cs.CV")
    ai = sum(1 for p in data if p.get("category") == "cs.AI")
    print(f"Backfill complete: {cv} CV, {ai} AI, {len(data) - cv - ai} other")
    return data

def summarize_paper(paper: Dict) -> Dict:
    system_prompt = """
You are a professional AI researcher. Analyze the following paper abstract and produce a structured JSON summary in Simplified Chinese.

Return ONLY valid JSON with exactly these fields (all string values must be in Simplified Chinese, except that proper nouns and method names may remain in English):
{
    "tags": ["tag1", "tag2", "tag3"],
    "tldr": "一句话中文总结",
    "motivation": "研究动机与要解决的问题",
    "method": "核心方法与技术路线",
    "result": "主要实验结果与量化指标",
    "conclusion": "结论、贡献与潜在影响"
}

Rules:
- "tags" should contain 3 to 5 concise English tags (e.g., SLAM, NeRF, Localization).
- "tldr" must be a single Chinese sentence within 80 characters.
- motivation / method / result / conclusion should each be 1-3 Chinese sentences; be specific and information-dense, avoid generic wording.
- If the abstract does not contain enough information for a field, write "摘要未提供相关信息" for that field.
"""
    user_prompt = f"""
Paper Title: {paper['title']}
Abstract: {paper['abstract']}
"""

    max_retries = 5
    base_delay = 10

    summary = None
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=MODEL_ID,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            summary = json.loads(response.choices[0].message.content)
            break
        except Exception as e:
            if "429" in str(e) or "rate" in str(e).lower():
                wait_time = base_delay * (2 ** attempt)
                print(f"DeepSeek rate limit hit for '{paper['title']}'. Waiting {wait_time}s (Attempt {attempt + 1}/{max_retries})...")
                time.sleep(wait_time)
            else:
                print(f"Error summarizing {paper['title']}: {e}")
                break
    else:
        print(f"Failed to summarize '{paper['title']}' after {max_retries} retries.")

    defaults = {
        "tags": ["Unknown"],
        "tldr": "摘要生成失败。",
        "motivation": "摘要未提供相关信息",
        "method": "摘要未提供相关信息",
        "result": "摘要未提供相关信息",
        "conclusion": "摘要未提供相关信息",
    }
    if summary is None:
        paper.update(defaults)
    else:
        for k, v in defaults.items():
            paper[k] = summary.get(k, v) or v

    time.sleep(1)
    return paper

def update_data(new_papers: List[Dict]):
    if not os.path.exists("docs"):
        os.makedirs("docs")

    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = []

    data = backfill_categories(data)

    existing_ids = {p["id"] for p in data}
    papers_to_summarize = [p for p in new_papers if p["id"] not in existing_ids]
    if len(papers_to_summarize) > MAX_PAPERS_PER_RUN:
        print(f"Truncating new papers from {len(papers_to_summarize)} to MAX_PAPERS_PER_RUN={MAX_PAPERS_PER_RUN}")
        papers_to_summarize = papers_to_summarize[:MAX_PAPERS_PER_RUN]

    print(f"Starting summarization for {len(papers_to_summarize)} new papers...")
    for i, p in enumerate(papers_to_summarize):
        print(f"[{i+1}/{len(papers_to_summarize)}] Summarizing: {p['title']}")
        summarized_p = summarize_paper(p)
        data.append(summarized_p)

    extended_fields = ("motivation", "method", "result", "conclusion")
    stale = [p for p in data if any(f not in p or not p.get(f) for f in extended_fields)]
    if stale:
        batch = stale[:BACKFILL_LIMIT]
        print(f"Backfilling extended summary fields for {len(batch)}/{len(stale)} existing papers (limit={BACKFILL_LIMIT})...")
        for i, p in enumerate(batch):
            print(f"[{i+1}/{len(batch)}] Backfill: {p['title']}")
            summarize_paper(p)

    data.sort(key=lambda x: x["published"], reverse=True)

    today = datetime.datetime.now()
    threshold_date = (today - datetime.timedelta(days=MAX_DAYS)).strftime("%Y-%m-%d")
    data = [p for p in data if p["published"] >= threshold_date]

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    if not DEEPSEEK_API_KEY:
        print("DEEPSEEK_API_KEY not found in environment or .env file.")
    else:
        print("Fetching papers from Arxiv...")
        papers = get_papers()
        print(f"Found {len(papers)} papers within the time window.")
        update_data(papers)
        print("Data updated successfully.")
