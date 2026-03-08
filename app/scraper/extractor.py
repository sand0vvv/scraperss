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
2. Open Graph tags — reliable for title, description, primary image
3. Meta description — often a clean product summary
4. Page text — richest source but noisiest; use for benefits, specs, ingredients, and anything missing from sources above
5. Image URLs — filter heavily; most are not product images

EXTRACTION RULES:

product_name — The full product name as a customer would recognize it. Do not include the brand name as a prefix unless it is part of the official product name. Do not include promotional text ("NEW!", "Best Seller", "Sale"). Prefer JSON-LD "name" field when available.

brand_name — The manufacturer or brand. Check JSON-LD "brand" field first, then OG site_name, then infer from page content. If genuinely unidentifiable, return empty string.

description — A concise 2-4 sentence summary capturing what the product is, what it does, and why someone would buy it. Write in the same language as the source page. Do not copy marketing fluff verbatim — distill the actual value proposition.

key_benefits — 3-7 specific, concrete benefits. Extract from bullet points, feature lists, or product description. Each benefit should be a short phrase, not a full sentence. If the page lists no explicit benefits, infer the most important ones from features and description. Never pad with generic filler ("High quality", "Great value").

price — The current selling price including currency symbol, exactly as displayed (e.g., "$29.99", "49,90 EUR"). If there is a sale/discount, use the discounted price. If price is a range, use the starting price with a "from" prefix (e.g., "from $19.99"). If free, return "Free". If no price is found on the page, return empty string.

product_images — URLs of actual product photos only. Maximum 10. Exclude: logos, icons, banners, UI elements, payment badges, social media icons, decorative graphics, tracking pixels. When the same image appears in multiple sizes, keep only the largest version. Prefer images from JSON-LD "image" field.

category — A specific product category describing what this item IS, at the level a shopper would use (e.g., "Wireless Headphones", "Face Moisturizer", "Running Shoes", "Espresso Machine"). Not too broad ("Electronics") and not too narrow.

target_audience — Who this product is designed for, if the page makes it clear (e.g., "professional photographers", "people with sensitive skin"). Return null if the page does not indicate a specific audience.

ingredients — Ingredients or composition list as a single string, applicable to food, cosmetics, supplements, and similar products. Return null for products where ingredients do not apply (electronics, clothing, furniture, etc.). Do not put technical specs or materials here.

specs — Key technical specifications as a flat object with string keys and string values. Extract from spec tables, feature lists, or product details sections. Include dimensions, weight, materials, compatibility, capacity, and similar factual attributes. Return null if no specs are found.

CRITICAL CONSTRAINTS:
- Extract ONLY information present on the page. Never fabricate data.
- Return ONLY the JSON object. No markdown fences, no explanation, no commentary.
- All string values must be properly escaped for valid JSON.
- If the page is not a product page (category listing, blog post, homepage, error page), return JSON with product_name set to empty string.
- For required string fields with no data, use empty string. For optional fields (target_audience, ingredients, specs), use null.

REQUIRED JSON STRUCTURE:
{"product_name": string, "brand_name": string, "description": string, "key_benefits": [string, ...], "price": string, "product_images": [string, ...], "category": string, "target_audience": string or null, "ingredients": string or null, "specs": {"key": "value", ...} or null}"""


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

    if parsed.json_ld:
        json_ld_str = json.dumps(parsed.json_ld, indent=2, default=str)
        # Truncate JSON-LD if too large
        if len(json_ld_str) > 5000:
            json_ld_str = json_ld_str[:5000] + "\n[...truncated]"
        parts.append(f"JSON-LD Data:\n{json_ld_str}")

    if parsed.image_urls:
        parts.append(f"Image URLs:\n" + "\n".join(parsed.image_urls[:30]))

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

                return ScrapeResponse(**product_data)

            except (json.JSONDecodeError, KeyError, TypeError) as e:
                last_error = e
                logger.warning(
                    "Attempt %d: Failed to parse LLM response: %s",
                    attempt + 1,
                    e,
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
