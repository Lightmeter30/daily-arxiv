import arxiv
from openai import OpenAI
import json
import os
import datetime
import time
from dateutil import tz
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()

# Configuration
KEYWORDS = [
    "3D Reconstruction",
    "SLAM",
    "VIO",
    "Visual Inertial Odometry",
    "Camera Localization",
    "Visual Localization",
    "Computer Vision",
    "Deep Learning",
    "Foundation Model",
    "Scene Understanding"
]
CATEGORIES = ["cs.CV", "cs.AI"]
MAX_DAYS = 7
DATA_FILE = "docs/data.json"

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
MODEL_ID = "deepseek-chat"

def get_papers() -> List[Dict]:
    query = " OR ".join([f'"{k}"' for k in KEYWORDS])
    search_query = f"({query}) AND (" + " OR ".join([f"cat:{c}" for c in CATEGORIES]) + ")"

    arxiv_client = arxiv.Client(
        page_size=50,
        delay_seconds=3,
        num_retries=3
    )

    search = arxiv.Search(
        query=search_query,
        max_results=50,
        sort_by=arxiv.SortCriterion.SubmittedDate
    )

    results = []
    threshold = datetime.datetime.now(tz.tzutc()) - datetime.timedelta(days=3)

    try:
        for result in arxiv_client.results(search):
            if result.published > threshold:
                paper_cats = [c for c in result.categories if c in CATEGORIES]
                category = paper_cats[0] if paper_cats else "Unknown"
                results.append({
                    "id": result.entry_id,
                    "title": result.title,
                    "authors": [a.name for a in result.authors],
                    "abstract": result.summary,
                    "link": result.entry_id,
                    "published": result.published.strftime("%Y-%m-%d"),
                    "category": category
                })
    except Exception as e:
        print(f"Error fetching from Arxiv: {e}")

    return results

def backfill_categories(data: List[Dict]) -> List[Dict]:
    """Batch-fetch category metadata for papers that lack it."""
    stale = [p for p in data if p.get("category", "Unknown") == "Unknown"]
    if not stale:
        return data

    print(f"Backfilling categories for {len(stale)} existing papers...")
    ids = [p["id"].split("/abs/")[-1] for p in stale]

    ac = arxiv.Client(page_size=len(ids), delay_seconds=3, num_retries=3)
    id_to_cat = {}
    try:
        for result in ac.results(arxiv.Search(id_list=ids)):
            paper_cats = [c for c in result.categories if c in CATEGORIES]
            id_to_cat[result.entry_id] = paper_cats[0] if paper_cats else "Unknown"
    except Exception as e:
        print(f"Error backfilling categories: {e}")
        return data

    for p in data:
        if p.get("category", "Unknown") == "Unknown":
            p["category"] = id_to_cat.get(p["id"], "Unknown")

    cv = sum(1 for p in data if p.get("category") == "cs.CV")
    ai = sum(1 for p in data if p.get("category") == "cs.AI")
    print(f"Backfill complete: {cv} CV, {ai} AI, {len(data) - cv - ai} other")
    return data

def summarize_paper(paper: Dict) -> Dict:
    system_prompt = """
You are a professional AI researcher. Analyze the following paper abstract and provide:
1. A list of 3-5 concise tags (e.g., SLAM, NeRF, Localization).
2. A one-sentence TL;DR summary in Chinese.

Output ONLY valid JSON:
{
    "tags": ["tag1", "tag2"],
    "tldr": "TL;DR content"
}
"""
    user_prompt = f"""
Paper Title: {paper['title']}
Abstract: {paper['abstract']}
"""

    max_retries = 5
    base_delay = 10

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
            paper.update(summary)
            break
        except Exception as e:
            if "429" in str(e) or "rate" in str(e).lower():
                wait_time = base_delay * (2 ** attempt)
                print(f"DeepSeek rate limit hit for '{paper['title']}'. Waiting {wait_time}s (Attempt {attempt + 1}/{max_retries})...")
                time.sleep(wait_time)
            else:
                print(f"Error summarizing {paper['title']}: {e}")
                paper["tags"] = ["Unknown"]
                paper["tldr"] = "Summary generation failed."
                break
    else:
        print(f"Failed to summarize '{paper['title']}' after {max_retries} retries.")
        paper["tags"] = ["Quota Limit"]
        paper["tldr"] = "Summary unavailable due to API quota exhaustion."

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

    print(f"Starting summarization for {len(papers_to_summarize)} new papers...")
    for i, p in enumerate(papers_to_summarize):
        print(f"[{i+1}/{len(papers_to_summarize)}] Summarizing: {p['title']}")
        summarized_p = summarize_paper(p)
        data.append(summarized_p)

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
