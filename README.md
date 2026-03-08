# Product URL Scraper

Standalone microservice that accepts any product page URL and returns structured JSON with product data (name, brand, price, description, images, specs, and more). Designed to be called by a backend service or used as part of a data pipeline.

## How It Works

```
URL → Playwright (headless Chromium) → BeautifulSoup (HTML parsing) → LLM (structured extraction) → Pydantic (validation) → JSON
```

1. **Browser rendering** — Playwright loads the page with headless Chromium, executing JavaScript to handle SPAs and dynamically-rendered content
2. **HTML parsing** — BeautifulSoup extracts structured data from multiple sources: JSON-LD, Open Graph meta tags, `<meta>` descriptions, image URLs, and cleaned page text
3. **LLM extraction** — Parsed data is sent to an LLM (via OpenRouter API) with a specialized prompt that prioritizes reliable data sources (JSON-LD > OG tags > meta > page text)
4. **Validation** — Pydantic v2 validates the LLM response against a strict schema before returning

## Tech Stack

- **Python 3.11+**
- **FastAPI** + **Uvicorn** — async web framework
- **Playwright** — headless Chromium for page rendering
- **BeautifulSoup4** + **lxml** — HTML parsing
- **OpenRouter API** — LLM provider (supports any model: Gemini, Claude, Llama, etc.)
- **Pydantic v2** — response validation
- **Docker** — containerized deployment

## Project Structure

```
app/
├── main.py              # FastAPI application, endpoint definitions
├── config.py            # Environment-based configuration (Pydantic Settings)
├── scraper/
│   ├── browser.py       # Playwright: page loading, HTML retrieval
│   ├── parser.py        # BeautifulSoup: meta tags, JSON-LD, images, text extraction
│   └── extractor.py     # LLM prompt and OpenRouter API integration
└── models/
    └── schemas.py       # Pydantic models for request/response validation
```

## Quick Start

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Configure environment
cp .env.example .env
# Edit .env — set your OPENROUTER_API_KEY

# Run the server
uvicorn app.main:app --reload
```

The service will be available at `http://localhost:8000`.

### Docker

```bash
docker build -t product-scraper .
docker run -p 8080:8080 --env-file .env product-scraper
```

### Deploy to Railway

1. Connect your GitHub repository to [Railway](https://railway.app)
2. Add the `OPENROUTER_API_KEY` environment variable in Railway dashboard
3. Railway will auto-detect the Dockerfile and deploy

## API Reference

### `GET /health`

Health check endpoint.

**Response:**
```json
{"status": "ok"}
```

### `POST /scrape`

Scrape a product page and return structured data.

**Request:**
```json
{
  "url": "https://theordinary.com/en-us/niacinamide-10-zinc-1-serum-100436.html"
}
```

**Response:**
```json
{
  "product_name": "Niacinamide 10% + Zinc 1%",
  "brand_name": "The Ordinary",
  "description": "A universal serum for blemish-prone skin that smooths, brightens, and supports. This formula helps to reduce the appearance of blemishes, congestion, and excess oil.",
  "key_benefits": [
    "Improves skin smoothness",
    "Reinforces skin barrier",
    "Radiant complexion",
    "Reduces appearance of blemishes",
    "Reduces appearance of congestion",
    "Reduces appearance of excess oil"
  ],
  "price": "$6.00",
  "price_original": null,
  "currency_code": "USD",
  "sku": "100436",
  "availability": "InStock",
  "rating": 4.5,
  "review_count": 1234,
  "product_images": [
    "https://theordinary.com/dw/image/v2/BFKJ_PRD/on/demandware.static/-/Sites-deciem-master/default/dwce8a7cdf/Images/products/The%20Ordinary/rdn-niacinamide-10pct-zinc-1pct-30ml.png?sw=900&sh=900&sm=fit"
  ],
  "category": "Serum",
  "raw_url": "https://theordinary.com/en-us/niacinamide-10-zinc-1-serum-100436.html",
  "target_audience": null,
  "ingredients": null,
  "specs": null
}
```

**Error Response (400 — page load failed):**
```json
{
  "detail": "HTTP 403 when loading https://example.com/product"
}
```

**Error Response (500 — extraction failed):**
```json
{
  "detail": "Failed to extract product data after 3 attempts: ..."
}
```

### Response Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `product_name` | `string` | Yes | Full product name |
| `brand_name` | `string` | Yes | Brand or manufacturer |
| `description` | `string` | Yes | Concise 2-4 sentence summary |
| `key_benefits` | `string[]` | Yes | 3-7 concrete product benefits |
| `price` | `string` | Yes | Price with currency symbol (e.g., `"$29.99"`, `"from $19.99"`) or empty string |
| `product_images` | `string[]` | Yes | Up to 10 product photo URLs (no icons/logos) |
| `category` | `string` | Yes | Product category (e.g., `"Smartphone"`, `"Face Moisturizer"`) |
| `raw_url` | `string` | Yes | The original URL that was scraped |
| `target_audience` | `string \| null` | No | Target audience, if identifiable |
| `ingredients` | `string \| null` | No | Ingredients list (food, cosmetics, supplements) |
| `specs` | `object \| null` | No | Technical specifications as key-value pairs |
| `currency_code` | `string \| null` | No | ISO 4217 currency code (e.g., `"USD"`, `"EUR"`) |
| `sku` | `string \| null` | No | Product SKU or identifier |
| `availability` | `string \| null` | No | Stock status: `InStock`, `OutOfStock`, `PreOrder`, `BackOrder`, `LimitedAvailability` |
| `rating` | `number \| null` | No | Average rating (e.g., `4.5`) |
| `review_count` | `integer \| null` | No | Total number of reviews |
| `price_original` | `string \| null` | No | Original price before discount (e.g., `"$39.99"`) |

## Configuration

All settings are configured via environment variables (or `.env` file):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENROUTER_API_KEY` | Yes | — | Your [OpenRouter](https://openrouter.ai) API key |
| `LLM_MODEL` | No | `google/gemini-2.5-flash-lite` | OpenRouter model ID ([browse models](https://openrouter.ai/models)) |
| `LLM_MAX_TOKENS` | No | `4096` | Maximum tokens for LLM response |
| `BROWSER_TIMEOUT` | No | `45000` | Page load timeout in milliseconds |
| `HOST` | No | `0.0.0.0` | Server bind address |
| `PORT` | No | `8080` | Server port |

### Recommended Models

| Model | OpenRouter ID | Cost (per 1M tokens) | Notes |
|-------|--------------|----------------------|-------|
| Gemini 2.5 Flash Lite | `google/gemini-2.5-flash-lite` | ~$0.25 / $1.50 | Best value, fast |
| Gemini 3 Flash | `google/gemini-3-flash-preview` | ~$0.50 / $3.00 | Higher quality |
| Claude Haiku 4.5 | `anthropic/claude-haiku-4.5` | $1 / $5 | Reliable, more expensive |
| Llama 3.3 70B | `meta-llama/llama-3.3-70b-instruct:free` | Free | Rate-limited (200 req/day) |

## Architecture

### Data Extraction Pipeline

The extraction prompt uses a **source priority system** to maximize accuracy:

1. **JSON-LD** (highest priority) — structured data embedded by the site; most reliable for name, brand, price
2. **Microdata** — schema.org `itemprop` attributes; reliable for SKU, brand, rating, availability
3. **Open Graph tags** — reliable for title, description, primary image
4. **Twitter Card tags** — fallback for title, description, image
5. **Meta description** — often contains a clean product summary
6. **Page text** (lowest priority) — richest but noisiest source; used for benefits, specs, and filling gaps

### HTML Cleaning

Before sending to the LLM, HTML is processed to reduce noise and token usage:
- Scripts, styles, navigation, headers, and footers are removed
- Text is extracted and deduplicated
- Content is truncated to ~40,000 characters
- JSON-LD is capped at 5,000 characters
- Image URLs are deduplicated, noise-filtered (logos, icons, trackers excluded), and limited to 15

### Error Handling

- **Browser errors** (timeout, HTTP 4xx/5xx) return `400` with details
- **LLM extraction failures** are retried up to 2 times before returning `500`
- **Validation errors** (invalid LLM output) trigger retries with the same prompt

## Limitations

- **Bot detection** — Anti-detection measures (stealth mode, realistic headers) handle most sites, but some heavily protected sites may still block or return CAPTCHAs.
- **Heavy pages** — Uses `domcontentloaded` wait strategy with a short JS rendering delay; most pages load within the 45s default timeout.
- **Rate limits** — Free OpenRouter models are limited to ~20 requests/minute and 200 requests/day.
- **Accuracy** — LLM extraction is not 100% deterministic. Edge cases (multi-variant products, bundle pages, non-standard layouts) may produce imperfect results.

## Usage Example (Python)

```python
import httpx

response = httpx.post(
    "https://your-deployment.up.railway.app/scrape",
    json={"url": "https://www.gymshark.com/products/gymshark-vital-seamless-t-shirt-ss-tops-grey-ss25"}
)

product = response.json()
print(f"{product['brand_name']} — {product['product_name']}: {product['price']}")
# Gymshark — Vital Seamless T-Shirt: $38
```

## Usage Example (cURL)

```bash
curl -X POST https://your-deployment.up.railway.app/scrape \
  -H "Content-Type: application/json" \
  -d '{"url": "https://store.google.com/product/pixel_9_pro"}'
```
