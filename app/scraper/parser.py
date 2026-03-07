import json
import logging
from dataclasses import dataclass, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class ParsedPage:
    title: str = ""
    meta_description: str = ""
    og_tags: dict[str, str] = field(default_factory=dict)
    json_ld: list[dict] = field(default_factory=list)
    image_urls: list[str] = field(default_factory=list)
    cleaned_text: str = ""


def parse_html(html: str, page_title: str, base_url: str) -> ParsedPage:
    """Extract structured data from HTML: meta tags, OG, JSON-LD, images, clean text."""
    soup = BeautifulSoup(html, "lxml")
    result = ParsedPage(title=page_title)

    # Meta description
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        result.meta_description = meta_desc["content"]

    # Open Graph tags
    for tag in soup.find_all("meta", attrs={"property": lambda v: v and v.startswith("og:")}):
        key = tag.get("property", "")
        value = tag.get("content", "")
        if key and value:
            result.og_tags[key] = value

    # JSON-LD structured data
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, list):
                result.json_ld.extend(data)
            else:
                result.json_ld.append(data)
        except (json.JSONDecodeError, TypeError):
            continue

    # Image URLs — collect from common product image patterns
    seen_urls: set[str] = set()
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if not src or src.startswith("data:"):
            continue
        absolute_url = urljoin(base_url, src)
        if absolute_url not in seen_urls:
            seen_urls.add(absolute_url)
            result.image_urls.append(absolute_url)

    # Clean text — remove scripts, styles, nav, footer, then extract text
    for tag in soup.find_all(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)
    # Collapse multiple blank lines
    lines = [line for line in text.splitlines() if line.strip()]
    result.cleaned_text = "\n".join(lines)

    # Truncate to ~15k chars to keep LLM context reasonable
    if len(result.cleaned_text) > 15000:
        result.cleaned_text = result.cleaned_text[:15000] + "\n[...truncated]"

    return result
