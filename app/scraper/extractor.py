import asyncio
import json
import logging

import httpx

from app.config import settings
from app.models.schemas import ScrapeResponse
from app.scraper.parser import ParsedPage

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

EXTRACTION_PROMPT = """\
You are a product data extraction system. You receive pre-parsed webpage data (metadata, structured data, images, text) and return a single JSON object with product information.

DATA SOURCE PRIORITY (most to least reliable):
1. JSON-LD — structured data embedded by the site; use as primary source for name, brand, price, description, images
2. Microdata — schema.org itemprop attributes; reliable for brand, price
3. Open Graph tags — reliable for title, description, primary image
4. Twitter Card tags — fallback for title, description, image
5. Meta description — often a clean product summary
6. Page text — richest source but noisiest; use for benefits, specs, ingredients, and anything missing from sources above
7. Image URLs — filter heavily; most are not product images

EXTRACTION RULES:

product_name — The full product name as a customer would recognize it. Do not include the brand name as a prefix unless it is part of the official product name. Do not include promotional text ("NEW!", "Best Seller", "Sale"). Prefer JSON-LD "name" field when available.

brand_name — The manufacturer or brand. Check JSON-LD "brand" field first, then microdata "brand", then OG site_name, then infer from page content. If genuinely unidentifiable, return empty string.

description — A concise 2-4 sentence summary capturing what the product is, what it does, and why someone would buy it. Write in the same language as the source page. Do not copy marketing fluff verbatim — distill the actual value proposition.

key_benefits — 3-7 specific, concrete benefits. Extract from bullet points, feature lists, or product description. Each benefit should be a short phrase, not a full sentence. If the page lists no explicit benefits, infer the most important ones from features and description. Never pad with generic filler ("High quality", "Great value").

price — The current selling price including currency symbol, exactly as displayed (e.g., "$29.99", "49,90 EUR"). Check these sources in order: JSON-LD "offers.price" or "offers.lowPrice", microdata "price", then SCAN the page text for price patterns (dollar/euro/pound signs followed by numbers). On Amazon, look for the main displayed price near the product title, ignoring "list price" or "was" prices (those go in price_original). If there is a sale/discount, use the discounted price. If price is a range, use the starting price with a "from" prefix (e.g., "from $19.99"). If free, return "Free". Return empty string ONLY if you are certain no price appears anywhere in the provided data.

price_original — The original price before any discount or sale, including currency symbol (e.g., "$39.99"). Return null if there is no discount or if the original price is the same as the current price.

product_images — Return exactly 2-3 product photo URLs. You MUST return at least 2 images if any product images exist on the page. Strategy: (1) Start with JSON-LD "image" field — this often contains multiple product images in an array. (2) Add the OG image if different. (3) Fill remaining slots from the Image URLs list, picking the largest/highest-resolution versions (prefer URLs containing "large", "zoom", "1024", "2048"; avoid "thumb", "small", "_SR38", "_AC_US40_"). Exclude: logos, icons, banners, UI elements, payment badges, decorative graphics. Maximum 3 URLs.

category — A specific product category describing what this item IS, at the level a shopper would use (e.g., "Wireless Headphones", "Facial Serum", "Running Shoes", "Espresso Machine"). Derive the category from the product name and page content — if the product name says "serum", the category must reflect that, not a different product type. Check JSON-LD "@type" or "category" fields and breadcrumb navigation for hints. Not too broad ("Electronics") and not too narrow ("Red Running Shoes Size 10").

target_audience — Who this product is designed for, if the page makes it clear (e.g., "professional photographers", "people with sensitive skin"). Return null if the page does not indicate a specific audience.

ingredients — The COMPLETE ingredients or composition list as a single comma-separated string, exactly as listed on the page (e.g., the full INCI list for cosmetics, full nutrition ingredients for food). Do NOT abbreviate to just active/hero ingredients — include every ingredient in the list. ONLY for products that are consumed or applied to the body: food, drinks, cosmetics, skincare, supplements, medicine. Return null for EVERYTHING else — clothing, electronics, furniture, accessories, shoes, bags, etc. Fabric composition (e.g., "65% Nylon, 35% Polyester") is NOT ingredients — put that in specs under "Material".

specs — Exactly 5-7 of the MOST IMPORTANT technical specifications as a flat object. Never exceed 7 entries. Focus on what a buyer cares about most: size/dimensions, weight, material/fabric, color, capacity, key technical features. Each value must be under 80 characters — if longer, shorten to the essential fact (e.g., "Up to 6 hours, 30 hours with case" not a paragraph). Use short key names (e.g., "Battery Life", "Weight", "Material", "Color", "Connectivity"). Skip compatibility lists, regulatory info, box contents, and manufacturer codes. Return null if no specs are found.

SITE-SPECIFIC HINTS:
- Amazon: Price is often in JSON-LD "offers.price" or in page text near "$XX.XX" patterns. Product images are in JSON-LD "image" array; prefer URLs containing "/images/I/" — these are full-size. Ignore thumbnails with "_SR38" or "_AC_US40_" in the URL.
- Shopify stores (Gymshark, Bombas, etc.): JSON-LD is usually comprehensive. Product images are in JSON-LD "image" array with multiple variants. Look for "cdn.shopify.com" URLs at their largest resolution.

CRITICAL CONSTRAINTS:
- Extract ONLY information present on the page. Never fabricate data.
- Return ONLY the JSON object. No markdown fences, no explanation, no commentary.
- All string values must be properly escaped for valid JSON.
- If the page is not a product page (category listing, blog post, homepage, error page), return JSON with product_name set to empty string.
- For required string fields with no data, use empty string. For optional fields, use null.

REQUIRED JSON STRUCTURE:
{"product_name": string, "brand_name": string, "description": string, "key_benefits": [string, ...], "price": string, "price_original": string or null, "product_images": [string, ...], "category": string, "target_audience": string or null, "ingredients": string or null, "specs": {"key": "value", ...} or null}"""


def _build_user_message(parsed: ParsedPage, url: str) -> str:
    """Build the user message with all extracted page data."""
    parts = [
        f"URL: {url}",
        f"Page Title: {parsed.title}",
    ]

    if parsed.meta_description:
        parts.append(f"Meta Description: {parsed.meta_description}")

    if parsed.og_tags:
        parts.append(f"Open Graph Tags:\n{json.dumps(parsed.og_tags, indent=2)}")

    if parsed.twitter_tags:
        parts.append(f"Twitter Card Tags:\n{json.dumps(parsed.twitter_tags, indent=2)}")

    if parsed.json_ld:
        json_ld_str = json.dumps(parsed.json_ld, indent=2, default=str)
        # Truncate JSON-LD if too large
        if len(json_ld_str) > 5000:
            json_ld_str = json_ld_str[:5000] + "\n[...truncated]"
        parts.append(f"JSON-LD Data:\n{json_ld_str}")

    if parsed.microdata:
        parts.append(f"Microdata (schema.org):\n{json.dumps(parsed.microdata, indent=2)}")

    if parsed.image_urls:
        parts.append(f"Image URLs:\n" + "\n".join(parsed.image_urls[:10]))

    parts.append(f"Page Text:\n{parsed.cleaned_text}")

    return "\n\n---\n\n".join(parts)


async def extract_product_data(
    parsed: ParsedPage,
    url: str,
    max_retries: int = 2,
) -> ScrapeResponse:
    """Send parsed page data to OpenRouter LLM and return validated product data."""
    user_message = _build_user_message(parsed, url)

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": settings.llm_model,
        "max_tokens": settings.llm_max_tokens,
        "messages": [
            {"role": "system", "content": EXTRACTION_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }

    last_error: Exception | None = None

    async with httpx.AsyncClient(timeout=60.0) as client:
        for attempt in range(max_retries + 1):
            try:
                response = await client.post(
                    OPENROUTER_URL,
                    headers=headers,
                    json=payload,
                )

                # Exponential backoff on 429 or 5xx
                if response.status_code == 429 or response.status_code >= 500:
                    delay = 2 ** (attempt + 1)  # 2s, 4s, 8s
                    logger.warning(
                        "Attempt %d: HTTP %d from OpenRouter, retrying in %ds",
                        attempt + 1,
                        response.status_code,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                response.raise_for_status()

                data = response.json()
                content = data["choices"][0]["message"]["content"]

                # Strip markdown code fences if present
                content = content.strip()
                if content.startswith("```"):
                    content = content.split("\n", 1)[1] if "\n" in content else content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()

                product_data = json.loads(content)
                product_data["raw_url"] = url

                # Coerce null to empty string for required string fields
                for field in ("product_name", "brand_name", "description", "price", "category"):
                    if product_data.get(field) is None:
                        product_data[field] = ""

                return ScrapeResponse(**product_data)

            except (json.JSONDecodeError, KeyError, TypeError) as e:
                last_error = e
                # Log the raw LLM response for debugging
                raw = content if "content" in dir() else "(no content)"
                logger.warning(
                    "Attempt %d: Failed to parse LLM response: %s\nRaw response: %.500s",
                    attempt + 1,
                    e,
                    raw,
                )
                continue
            except httpx.HTTPStatusError as e:
                logger.error("OpenRouter API error: %s", e.response.text)
                raise
            except Exception as e:
                last_error = e
                logger.warning("Attempt %d: Error: %s", attempt + 1, e)
                continue

    raise ValueError(
        f"Failed to extract product data after {max_retries + 1} attempts: {last_error}"
    )
