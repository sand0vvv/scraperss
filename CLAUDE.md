# Product URL Scraper

## What is this?

Standalone microservice that accepts a product page URL and returns structured JSON with product data. Designed to be called by a FastAPI backend.

## Tech Stack

- **Python 3.11+** with **FastAPI** + **Uvicorn**
- **Playwright** (headless Chromium) for page loading
- **BeautifulSoup4** + **lxml** for HTML parsing
- **OpenRouter API** (Claude Sonnet) for AI-powered data extraction
- **Pydantic v2** for validation
- **Docker** for deployment

## Project Structure

```
app/
├── main.py          # FastAPI app: POST /scrape, GET /health
├── config.py        # Settings from .env
├── scraper/
│   ├── browser.py   # Playwright: load page, get HTML
│   ├── parser.py    # BS4: extract meta, images, text, JSON-LD
│   └── extractor.py # OpenRouter LLM: structured extraction
└── models/
    └── schemas.py   # Pydantic models (request/response)
```

## How to Run

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env  # add your OPENROUTER_API_KEY
uvicorn app.main:app --reload
```

## Docker

```bash
docker build -t scraper .
docker run -p 8000:8000 --env-file .env scraper
```

## Pipeline

1. Playwright loads the URL (headless Chromium)
2. BeautifulSoup parses HTML → clean text, meta tags, images, JSON-LD
3. OpenRouter (Claude Sonnet) extracts structured product data
4. Pydantic validates the response

## Key Decisions

- Browser rendering via Playwright handles JS-heavy pages (SPAs, React shops)
- HTML is cleaned (no scripts/styles) before sending to LLM to reduce token usage
- JSON-LD and OG meta tags are extracted separately as reliable structured data sources
- LLM extraction handles the messy/ambiguous parts that rule-based parsing can't
