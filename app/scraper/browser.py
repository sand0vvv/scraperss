import logging

from playwright.async_api import async_playwright

from app.config import settings

logger = logging.getLogger(__name__)


class BrowserError(Exception):
    pass


async def fetch_page(url: str) -> dict[str, str]:
    """Load a URL with headless Chromium and return rendered HTML + page title."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 720},
            )
            page = await context.new_page()

            response = await page.goto(
                url,
                wait_until="networkidle",
                timeout=settings.browser_timeout,
            )

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
