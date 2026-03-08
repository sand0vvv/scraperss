import json
import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

IMAGE_NOISE_PATTERNS = re.compile(
    r"logo|icon|badge|pixel|tracker|\.gif|spacer|sprite|placeholder|1x1",
    re.IGNORECASE,
)


@dataclass
class ParsedPage:
    title: str = ""
    meta_description: str = ""
    og_tags: dict[str, str] = field(default_factory=dict)
    twitter_tags: dict[str, str] = field(default_factory=dict)
    json_ld: list[dict] = field(default_factory=list)
    microdata: dict[str, str] = field(default_factory=dict)
    image_urls: list[str] = field(default_factory=list)
    cleaned_text: str = ""


def _extract_microdata(soup: BeautifulSoup) -> dict[str, str]:
    """Extract schema.org microdata from itemprop attributes."""
    result: dict[str, str] = {}
    for el in soup.find_all(attrs={"itemprop": True}):
        prop = el["itemprop"]
        # Get value from content attribute (meta tags), or href/src, or text
        value = (
            el.get("content")
            or el.get("href")
            or el.get("src")
            or el.get_text(strip=True)
        )
        if value and prop not in result:
            result[prop] = value
    return result


def _best_srcset_url(srcset: str) -> str:
    """Pick the largest image URL from a srcset attribute."""
    best_url = ""
    best_width = 0
    for part in srcset.split(","):
        part = part.strip()
        if not part:
            continue
        tokens = part.split()
        if len(tokens) >= 2 and tokens[1].endswith("w"):
            try:
                width = int(tokens[1][:-1])
                if width > best_width:
                    best_width = width
                    best_url = tokens[0]
            except ValueError:
                continue
        elif len(tokens) >= 1 and not best_url:
            best_url = tokens[0]
    return best_url


def parse_html(html: str, page_title: str, base_url: str) -> ParsedPage:
    """Extract structured data from HTML: meta tags, OG, Twitter, JSON-LD, microdata, images, clean text."""
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

    # Twitter Card tags
    for tag in soup.find_all("meta", attrs={"name": lambda v: v and v.startswith("twitter:")}):
        key = tag.get("name", "")
        value = tag.get("content", "")
        if key and value:
            result.twitter_tags[key] = value

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

    # Microdata (schema.org itemprop attributes)
    result.microdata = _extract_microdata(soup)

    # Image URLs — collect from JSON-LD, srcset, and img tags, filter noise
    seen_urls: set[str] = set()

    def _add_image(url: str) -> None:
        if not url or url.startswith("data:"):
            return
        absolute = urljoin(base_url, url)
        if IMAGE_NOISE_PATTERNS.search(absolute):
            return
        if absolute not in seen_urls:
            seen_urls.add(absolute)
            result.image_urls.append(absolute)

    # 1. Images from JSON-LD (highest quality source)
    for item in result.json_ld:
        images = item.get("image", [])
        if isinstance(images, str):
            images = [images]
        elif isinstance(images, dict):
            images = [images.get("url", "")]
        for img_url in images[:5]:
            if isinstance(img_url, str):
                _add_image(img_url)
            elif isinstance(img_url, dict):
                _add_image(img_url.get("url", ""))

    # 2. Images from img tags (src, data-src, srcset)
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        _add_image(src)
        # Extract largest image from srcset
        srcset = img.get("srcset", "")
        if srcset:
            best_url = _best_srcset_url(srcset)
            if best_url:
                _add_image(best_url)
        if len(result.image_urls) >= 10:
            break

    # Clean text — remove scripts, styles, nav, footer, then extract text
    for tag in soup.find_all(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)
    # Collapse multiple blank lines
    lines = [line for line in text.splitlines() if line.strip()]
    result.cleaned_text = "\n".join(lines)

    # Truncate to ~40k chars to keep LLM context reasonable
    if len(result.cleaned_text) > 40000:
        result.cleaned_text = result.cleaned_text[:40000] + "\n[...truncated]"

    return result
