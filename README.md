# Product URL Scraper

Microservice that extracts structured product data from any product page URL.

Accepts a URL via `POST /scrape`, renders the page with headless Chromium, parses the HTML, and uses an LLM (Claude Sonnet via OpenRouter) to extract structured product information.

## Setup

### Local

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
# Edit .env — add your OPENROUTER_API_KEY
uvicorn app.main:app --reload
```

### Docker

```bash
docker build -t product-scraper .
docker run -p 8000:8000 --env-file .env product-scraper
```

## API

### `POST /scrape`

Request:
```json
{
  "url": "https://example.com/product/123"
}
```

Response:
```json
{
  "product_name": "Example Product",
  "brand_name": "Brand",
  "description": "Product description.",
  "key_benefits": ["Benefit 1", "Benefit 2"],
  "price": "$29.99",
  "product_images": ["https://..."],
  "category": "Electronics",
  "raw_url": "https://example.com/product/123",
  "target_audience": "Tech enthusiasts",
  "ingredients": null,
  "specs": null
}
```

### `GET /health`

Returns `{"status": "ok"}`.

## Architecture

1. **Browser** (Playwright) — loads the page with headless Chromium, waits for full render
2. **Parser** (BeautifulSoup) — extracts meta tags, Open Graph, JSON-LD, images, and cleaned text
3. **Extractor** (OpenRouter → Claude Sonnet) — LLM-based structured data extraction
4. **Validation** (Pydantic) — ensures response matches the expected schema

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENROUTER_API_KEY` | Yes | — | OpenRouter API key |
| `BROWSER_TIMEOUT` | No | `30000` | Page load timeout (ms) |
| `LLM_MODEL` | No | `anthropic/claude-sonnet-4` | OpenRouter model ID |
| `LLM_MAX_TOKENS` | No | `4096` | Max tokens for LLM response |

---

Built with Claude Code.
