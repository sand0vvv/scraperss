# Product URL Scraper

## What is this?

Standalone microservice that accepts a product page URL and returns structured JSON with product data for marketing strategy. Designed to be called by a FastAPI backend.

**Deployed at:** https://ambro717.up.railway.app
**Repo:** https://github.com/sand0vvv/scraperss

## Tech Stack

- **Python 3.11+** with **FastAPI** + **Uvicorn**
- **Playwright** + **playwright-stealth** (headless Chromium with anti-detection)
- **BeautifulSoup4** + **lxml** for HTML parsing
- **OpenRouter API** (Gemini 3 Flash) for AI-powered data extraction
- **Pydantic v2** for validation
- **Docker** for deployment (Railway)

## Project Structure

```
app/
├── main.py          # FastAPI app: POST /scrape, GET /health
├── config.py        # Settings from .env (model, timeout, etc.)
├── scraper/
│   ├── browser.py   # Playwright: stealth mode, anti-detection, domcontentloaded + delay
│   ├── parser.py    # BS4: JSON-LD, microdata, OG, Twitter, images (srcset/JSON-LD), text
│   └── extractor.py # OpenRouter LLM: extraction prompt, backoff, null coercion
└── models/
    └── schemas.py   # Pydantic models (request/response)
```

## Pipeline

1. Playwright loads the URL (headless Chromium, stealth mode, 45s timeout)
2. BeautifulSoup parses HTML → JSON-LD, microdata, OG tags, Twitter cards, images, clean text
3. OpenRouter (Gemini 3 Flash) extracts structured product data via specialized prompt
4. Pydantic validates the response

## Response Fields

Required: product_name, brand_name, description, key_benefits, price, product_images (2-3), category, raw_url
Optional: target_audience, ingredients, specs (5-7), price_original

## Key Decisions

- **Gemini 3 Flash** — best price/quality ratio (tested vs Haiku 4.5 and Gemini 2.5 Flash Lite)
- **domcontentloaded + 2s delay** instead of networkidle — prevents timeouts on heavy sites
- **playwright-stealth** + realistic headers — handles most anti-bot systems
- **7-source priority system** in prompt: JSON-LD > Microdata > OG > Twitter > Meta > Page text > Images
- **Site-specific hints** in prompt for Amazon and Shopify stores
- Images extracted from JSON-LD, srcset, and img tags — noise-filtered (logos, icons, trackers)
- Exponential backoff on 429/5xx from OpenRouter
- Null coercion for required string fields (LLM sometimes returns null)

## Known Limitations

- Amazon frequently blocks Railway cloud IPs with CAPTCHA (works intermittently)
- Gymshark returns only 1 product image from Shopify JSON-LD
- Some sites with aggressive bot detection may still block
