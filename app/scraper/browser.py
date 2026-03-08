import asyncio
import logging

from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

from app.config import settings

logger = logging.getLogger(__name__)


class BrowserError(Exception):
    pass


async def fetch_page(url: str) -> dict[str, str]:
    """Load a URL with headless Chromium and return rendered HTML + page title."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 720},
                extra_http_headers={
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                    "Sec-Fetch-User": "?1",
                    "Upgrade-Insecure-Requests": "1",
                },
            )
            page = await context.new_page()

            # Apply stealth patches to avoid bot detection
            await stealth_async(page)

            # Backup: patch navigator.webdriver property
            await page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            response = await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=settings.browser_timeout,
            )

            # Wait for JS rendering after DOM is ready
            await asyncio.sleep(2)

            if response is None:
                raise BrowserError(f"No response received from {url}")

            if response.status >= 400:
                raise BrowserError(
                    f"HTTP {response.status} when loading {url}"
                )

            html = await page.content()
            title = await page.title()

            return {"html": html, "title": title}
        finally:
            await browser.close()
