# Product URL Scraper

Standalone microservice that accepts any product page URL and returns structured JSON with product data (name, brand, price, description, images, specs, and more). Designed to be called by a backend service or used as part of a data pipeline.

## How It Works

```
URL → Playwright (headless Chromium) → BeautifulSoup (HTML parsing) → LLM (structured extraction) → Pydantic (validation) → JSON
```

1. **Browser rendering** — Playwright loads the page with headless Chromium (stealth mode, anti-detection), executing JavaScript to handle SPAs and dynamically-rendered content
2. **HTML parsing** — BeautifulSoup extracts structured data from multiple sources: JSON-LD, microdata, Open Graph, Twitter Card, meta tags, images, and cleaned page text
3. **LLM extraction** — Parsed data is sent to Gemini 3 Flash (via OpenRouter API) with a specialized prompt that prioritizes reliable data sources
4. **Validation** — Pydantic v2 validates the LLM response against a strict schema before returning

## Tech Stack

- **Python 3.11+**
- **FastAPI** + **Uvicorn** — async web framework
- **Playwright** + **playwright-stealth** — headless Chromium with anti-detection
- **BeautifulSoup4** + **lxml** — HTML parsing
- **OpenRouter API** (Gemini 3 Flash) — LLM-powered data extraction
- **Pydantic v2** — response validation
- **Docker** — containerized deployment

## LLM Model

The default model is **Google Gemini 3 Flash** (`google/gemini-3-flash-preview`).

We tested three models (Gemini 2.5 Flash Lite, Claude Haiku 4.5, Gemini 3 Flash) across diverse product pages (The Ordinary, Gymshark, Amazon, Google Store). Gemini 3 Flash had the best price-to-quality ratio:

- **Accurate extraction** — correctly extracts prices on Amazon (other models failed), proper category classification ("Facial Serum" not "Face Moisturizer"), concise specs within limits
- **Fast** — low latency via OpenRouter
- **Affordable** — ~$0.50 input / $3.00 output per 1M tokens. At beta volume (1-5 URLs/day), the cost is negligible

The model can be changed via the `LLM_MODEL` environment variable if needed.

## Project Structure

```
app/
├── main.py              # FastAPI application, endpoint definitions
├── config.py            # Environment-based configuration (Pydantic Settings)
├── scraper/
│   ├── browser.py       # Playwright: page loading with stealth/anti-detection
│   ├── parser.py        # BeautifulSoup: meta tags, JSON-LD, microdata, images, text
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
  "description": "A universal serum for blemish-prone skin that smooths, brightens, and supports. It improves skin smoothness and reinforces the skin barrier for a more radiant complexion.",
  "key_benefits": [
    "Improves skin brightness",
    "Smooths skin texture",
    "Reinforces skin barrier",
    "Supports blemish-prone skin",
    "Universal formulation"
  ],
  "price": "$6.00",
  "price_original": null,
  "product_images": [
    "https://theordinary.com/dw/image/v2/BFKJ_PRD/on/demandware.static/-/Sites-deciem-master/default/dwce8a7cdf/Images/products/The%20Ordinary/rdn-niacinamide-10pct-zinc-1pct-30ml.png",
    "https://theordinary.com/dw/image/v2/BFKJ_PRD/on/demandware.static/-/Sites-deciem-master/default/dw51b196c5/Images/products/The%20Ordinary/application/ord-niacinamide-10-zic-1-model-application-with-benefits.jpg",
    "https://theordinary.com/dw/image/v2/BFKJ_PRD/on/demandware.static/-/Sites-deciem-master/default/dwbf9b60a4/Images/products/The%20Ordinary/infographics/ord-niacainamide-zinc-blemish-serum-benefits-graphic.jpg"
  ],
  "category": "Facial Serum",
  "raw_url": "https://theordinary.com/en-us/niacinamide-10-zinc-1-serum-100436.html",
  "target_audience": "people with blemish-prone skin",
  "ingredients": "Niacinamide, Zinc PCA",
  "specs": {
    "Size": "30ml",
    "Format": "Water-based Serum",
    "Key Ingredients": "Niacinamide 10%, Zinc 1%",
    "Skin Type": "All Skin Types",
    "pH": "5.00 - 6.50"
  }
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
| `product_images` | `string[]` | Yes | 2-3 best product photo URLs (no icons/logos) |
| `category` | `string` | Yes | Product category (e.g., `"Facial Serum"`, `"Training T-Shirt"`) |
| `raw_url` | `string` | Yes | The original URL that was scraped |
| `target_audience` | `string \| null` | No | Target audience, if identifiable |
| `ingredients` | `string \| null` | No | Ingredients list (cosmetics, food, supplements only) |
| `specs` | `object \| null` | No | 5-7 key technical specifications as key-value pairs |
| `price_original` | `string \| null` | No | Original price before discount (e.g., `"$39.99"`) |

## Configuration

All settings are configured via environment variables (or `.env` file):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENROUTER_API_KEY` | Yes | — | Your [OpenRouter](https://openrouter.ai) API key |
| `LLM_MODEL` | No | `google/gemini-3-flash-preview` | OpenRouter model ID ([browse models](https://openrouter.ai/models)) |
| `LLM_MAX_TOKENS` | No | `4096` | Maximum tokens for LLM response |
| `BROWSER_TIMEOUT` | No | `45000` | Page load timeout in milliseconds |
| `HOST` | No | `0.0.0.0` | Server bind address |
| `PORT` | No | `8080` | Server port |

## Architecture

### Data Extraction Pipeline

The extraction prompt uses a **source priority system** to maximize accuracy:

1. **JSON-LD** (highest priority) — structured data embedded by the site; most reliable for name, brand, price
2. **Microdata** — schema.org `itemprop` attributes; reliable for brand, price
3. **Open Graph tags** — reliable for title, description, primary image
4. **Twitter Card tags** — fallback for title, description, image
5. **Meta description** — often contains a clean product summary
6. **Page text** — richest but noisiest source; used for benefits, specs, and filling gaps
7. **Image URLs** (lowest priority) — heavily filtered; most are not product images

### Anti-Detection

The browser module includes multiple anti-detection measures:
- **playwright-stealth** — patches common bot detection signals
- **Realistic headers** — Accept-Language, Sec-Fetch-*, Upgrade-Insecure-Requests
- **navigator.webdriver patch** — removes automation flag
- **domcontentloaded + delay** — avoids `networkidle` timeouts on heavy sites

### HTML Cleaning

Before sending to the LLM, HTML is processed to reduce noise and token usage:
- Scripts, styles, navigation, headers, and footers are removed
- Text is extracted and deduplicated
- Content is truncated to ~40,000 characters
- JSON-LD is capped at 5,000 characters
- Images are collected from JSON-LD, srcset, and img tags; noise-filtered and limited to 10 candidates

### Error Handling

- **Browser errors** (timeout, HTTP 4xx/5xx) return `400` with details
- **LLM extraction failures** are retried up to 2 times before returning `500`
- **Rate limiting** (429) and server errors (5xx) from OpenRouter trigger exponential backoff (2s, 4s, 8s)
- **Null coercion** — LLM returning `null` for required string fields is auto-corrected to empty string

## Limitations

- **Bot detection** — Anti-detection measures handle most sites (Amazon, Shopify, Google Store work well), but some heavily protected sites may still block or return CAPTCHAs.
- **Heavy pages** — Uses `domcontentloaded` wait strategy with a short JS rendering delay; most pages load within the 45s default timeout.
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
