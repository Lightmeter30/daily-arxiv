# Repository Guidelines

## Project Structure & Module Organization

This repository powers a static Daily Arxiv CV/AI Briefing site. Core automation lives in `scripts/`, generated public data and UI live in `docs/`, and scheduled jobs live in `.github/workflows/`.

- `scripts/fetch_and_summarize.py`: fetches matching arXiv papers, calls DeepSeek, and writes `docs/data.json`.
- `scripts/summarize_missing.py`: backfills missing summaries in existing records.
- `scripts/requirements.txt`: Python dependencies.
- `docs/index.html`: static GitHub Pages frontend.
- `docs/data.json`: rolling paper dataset consumed by the frontend.

## Build, Test, and Development Commands

Use the `daily-arxiv` conda environment for local testing and verification. The workflows use Python 3.12.

```bash
conda run -n daily-arxiv pip install -r scripts/requirements.txt
```

Installs runtime dependencies.

```bash
echo "DEEPSEEK_API_KEY=your_api_key" > .env
conda run -n daily-arxiv python scripts/fetch_and_summarize.py
```

Runs the daily fetch and summary pipeline locally, updating `docs/data.json`.

```bash
conda run -n daily-arxiv python scripts/summarize_missing.py --limit 20
```

Backfills up to 20 existing papers with missing AI summary fields.

```bash
python -m http.server 8000 -d docs
```

Serves the static site at `http://localhost:8000` for frontend checks.

## Coding Style & Naming Conventions

Follow standard Python style: 4-space indentation, clear function names, and uppercase constants or environment-backed settings such as `ARXIV_MAX_DAYS`. Keep scripts self-contained unless shared logic becomes substantial. In `docs/index.html`, preserve the existing Tailwind CDN approach and avoid introducing a build step without a strong reason.

## Testing Guidelines

There is currently no formal test suite or linter. Before submitting changes, run the affected script with a valid `.env` when API behavior is involved, and verify that `docs/data.json` remains valid JSON. For frontend changes, serve `docs/` locally and confirm the page loads data without console errors.

When running tests, always use the project conda environment:

```bash
conda run -n daily-arxiv python -m unittest tests/test_fetch_and_summarize.py
```

## Commit & Pull Request Guidelines

Use the existing Conventional Commit style:

- `feat: add summarize-missing action for backfilling AI summaries`
- `fix: add exponential backoff retry for arxiv 429 rate-limiting`
- `chore: daily arxiv update [2026-05-15]`

Pull requests should include a concise summary, the commands run for verification, and screenshots for visible `docs/index.html` changes. Note any changes to workflow schedules, environment variables, or API usage.

## Security & Configuration Tips

Never commit `.env`, API keys, or generated cache files. Configure `DEEPSEEK_API_KEY` through GitHub Actions secrets. Use repository variables for optional settings such as `ARXIV_KEYWORDS`, `ARXIV_CATEGORIES`, `ARXIV_MAX_DAYS`, and `DEEPSEEK_MODEL`.

## Agent-Specific Instructions

When working in this repository, communicate with maintainers in Chinese unless explicitly asked otherwise.
