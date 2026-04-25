import arxiv
from google import genai
import json
import os
import datetime
import time
from dateutil import tz
from typing import List, Dict

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

# Gemini setup using the NEW google-genai SDK
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_ID = "gemini-2.0-flash"

def get_papers() -> List[Dict]:
    query = " OR ".join([f'"{k}"' for k in KEYWORDS])
    search_query = f"({query}) AND (" + " OR ".join([f"cat:{c}" for c in CATEGORIES]) + ")"
    
    # Use the newer client-based approach for arxiv
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
    # Broaden threshold to last 3 days
    threshold = datetime.datetime.now(tz.tzutc()) - datetime.timedelta(days=3)
    
    # arxiv 2.0.0+ uses client.results(search)
    try:
        for result in arxiv_client.results(search):
            if result.published > threshold:
                results.append({
                    "id": result.entry_id,
                    "title": result.title,
                    "authors": [a.name for a in result.authors],
                    "abstract": result.summary,
                    "link": result.entry_id,
                    "published": result.published.strftime("%Y-%m-%d")
                })
    except Exception as e:
        print(f"Error fetching from Arxiv: {e}")
        
    return results

def summarize_paper(paper: Dict) -> Dict:
    prompt = f"""
    You are a professional AI researcher. Analyze the following paper abstract and provide:
    1. A list of 3-5 concise tags (e.g., SLAM, NeRF, Localization).
    2. A one-sentence TL;DR summary in Chinese.

    Output format: JSON
    {{
        "tags": ["tag1", "tag2"],
        "tldr": "TL;DR content"
    }}

    Paper Title: {paper['title']}
    Abstract: {paper['abstract']}
    """
    
    max_retries = 5
    base_delay = 10 # Initial wait time for 429 errors
    
    for attempt in range(max_retries):
        try:
            # Use new SDK generate_content call
            response = client.models.generate_content(
                model=MODEL_ID,
                contents=prompt,
                config={
                    "response_mime_type": "application/json"
                }
            )
            summary = json.loads(response.text)
            paper.update(summary)
            # Success, break retry loop
            break
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                wait_time = base_delay * (2 ** attempt)
                print(f"Gemini Rate limit (429) hit for '{paper['title']}'. Waiting {wait_time}s (Attempt {attempt + 1}/{max_retries})...")
                time.sleep(wait_time)
            else:
                print(f"Error summarizing {paper['title']}: {e}")
                paper["tags"] = ["Unknown"]
                paper["tldr"] = "Summary generation failed."
                break
    else:
        # Executed if the loop finished without 'break'
        print(f"Failed to summarize '{paper['title']}' after {max_retries} retries.")
        paper["tags"] = ["Quota Limit"]
        paper["tldr"] = "Summary unavailable due to Gemini API quota exhaustion."
    
    # General sleep between papers to stay within free tier limits (usually 10-15 RPM)
    time.sleep(2)
    return paper

def update_data(new_papers: List[Dict]):
    if not os.path.exists("docs"):
        os.makedirs("docs")
        
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = []

    # Filter out duplicates
    existing_ids = {p["id"] for p in data}
    papers_to_summarize = [p for p in new_papers if p["id"] not in existing_ids]

    # Summarize new papers
    print(f"Starting summarization for {len(papers_to_summarize)} new papers...")
    for i, p in enumerate(papers_to_summarize):
        print(f"[{i+1}/{len(papers_to_summarize)}] Summarizing: {p['title']}")
        summarized_p = summarize_paper(p)
        data.append(summarized_p)

    # Sort by date descending
    data.sort(key=lambda x: x["published"], reverse=True)

    # Keep only last 7 days
    today = datetime.datetime.now()
    threshold_date = (today - datetime.timedelta(days=MAX_DAYS)).strftime("%Y-%m-%d")
    data = [p for p in data if p["published"] >= threshold_date]

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    if not GEMINI_API_KEY:
        print("GEMINI_API_KEY not found in environment variables.")
    else:
        print("Fetching papers from Arxiv...")
        papers = get_papers()
        print(f"Found {len(papers)} papers within the time window.")
        update_data(papers)
        print("Data updated successfully.")
