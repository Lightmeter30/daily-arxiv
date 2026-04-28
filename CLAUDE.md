# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Daily Arxiv CV/AI Briefing — fetches recent arxiv papers in CV/AI (3D reconstruction, SLAM, VIO, camera localization, etc.), uses DeepSeek to generate Chinese TL;DR summaries and tags, and publishes results as a static JSON-powered page via GitHub Pages.

## Commands

```bash
# Install dependencies (Python 3.12)
pip install -r scripts/requirements.txt

# Run locally
# Option 1: .env file (recommended)
echo "DEEPSEEK_API_KEY=your_api_key" > .env

# Option 2: environment variable
export DEEPSEEK_API_KEY="your_api_key"
python scripts/fetch_and_summarize.py
```

No linter or test suite exists in this repo.

## Architecture

**Data flow**: Arxiv API → `scripts/fetch_and_summarize.py` → `docs/data.json` → `docs/index.html` (browser-side fetch).

- `scripts/fetch_and_summarize.py` — single self-contained script. Searches arxiv for papers matching `KEYWORDS` within `CATEGORIES` (cs.CV, cs.AI), filters to last 3 days, deduplicates against existing `docs/data.json` entries, calls DeepSeek for summarization (JSON mode), outputs the merged 7-day rolling window to `docs/data.json`. Implements exponential backoff (base 10s, 5 retries) for API rate limits, with a 1s cooldown between papers. Loads API key from `.env` file via python-dotenv.
- `docs/index.html` — static frontend using Tailwind CSS CDN. Loads `data.json` at runtime, groups papers by `published` date, renders cards with tags and TL;DR.
- `.github/workflows/daily_arxiv.yml` — triggers at UTC 00:00 (8am Beijing time) or manually via `workflow_dispatch`. Installs deps, runs the script, commits the updated `data.json`.

**Path note**: Both the workflow and the Python script use `docs/data.json` relative to the repo root. `actions/checkout` checks out into the repo root by default, so no prefix is needed.
