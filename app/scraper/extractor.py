import json
import logging

import httpx

from app.config import settings
from app.models.schemas import ScrapeResponse
from app.scraper.parser import ParsedPage

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

EXTRACTION_PROMPT = """\
You are a product data extraction specialist. Your task: extract structured product information from the provided webpage data and return it as a JSON object.

You will receive:
- Page title
- Meta description
- Open Graph tags
- JSON-LD structured data (if available)
- Image URLs found on the page
- Cleaned page text

Return ONLY a valid JSON object with these fields:

{
  "product_name": "Full product name as displayed on the page",
  "brand_name": "Brand or manufacturer name",
  "description": "Product description — concise summary (2-4 sentences). Capture the essence of what the product is and what it does.",
  "key_benefits": ["Benefit 1", "Benefit 2", ...],
  "price": "Price as shown on the page, including currency symbol (e.g., '$29.99'). Use empty string if not found.",
  "product_images": ["url1", "url2", ...],
  "category": "Product category (e.g., 'Electronics', 'Skincare', 'Kitchen Appliance')",
  "target_audience": "Who this product is for, or null if unclear",
  "ingredients": "Ingredients list or key specs as a string, or null if not applicable",
  "specs": {"key": "value"} or null if no specs found
}

Rules:
- Extract ONLY information present on the page. Never invent or hallucinate data.
- For product_images: select only product-relevant images. Exclude icons, logos, banners, UI elements. Prefer high-resolution images. Maximum 10 images.
- For key_benefits: extract 3-7 concrete benefits. If not explicitly listed, infer from description/features.
- For price: include the primary/current price. If there's a sale, use the sale price.
- If a field cannot be determined from the page, use empty string for strings and empty array for lists.
- Return raw JSON only — no markdown, no explanation, no code fences."""


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
