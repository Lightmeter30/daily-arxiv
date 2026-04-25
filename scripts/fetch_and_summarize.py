import arxiv
import google.generativeai as genai
import json
import os
import datetime
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

# Gemini setup
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash')

def get_papers() -> List[Dict]:
    query = " OR ".join([f'"{k}"' for k in KEYWORDS])
    search = arxiv.Search(
        query=f"({query}) AND (" + " OR ".join([f"cat:{c}" for c in CATEGORIES]) + ")",
        max_results=50,
        sort_by=arxiv.SortCriterion.SubmittedDate
    )
    
    results = []
    # Broaden threshold to last 3 days to ensure we don't miss papers due to timezone/weekend lags
    threshold = datetime.datetime.now(tz.tzutc()) - datetime.timedelta(days=3)
    
    for result in search.results():
        if result.published > threshold:
            results.append({
                "id": result.entry_id,
                "title": result.title,
                "authors": [a.name for a in result.authors],
                "abstract": result.summary,
                "link": result.entry_id,
                "published": result.published.strftime("%Y-%m-%d")
            })
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
    try:
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        summary = json.loads(response.text)
        paper.update(summary)
    except Exception as e:
        print(f"Error summarizing {paper['title']}: {e}")
        paper["tags"] = ["Unknown"]
        paper["tldr"] = "Summary generation failed."
    return paper

def update_data(new_papers: List[Dict]):
    if not os.path.exists("docs"):
        os.makedirs("docs")
        
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = []

    # Filter out duplicates and append new papers
    existing_ids = {p["id"] for p in data}
    for p in new_papers:
        if p["id"] not in existing_ids:
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
        print("Fetching papers...")
        papers = get_papers()
        print(f"Found {len(papers)} new papers. Summarizing...")
        update_data(papers)
        print("Data updated successfully.")
