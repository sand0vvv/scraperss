import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.models.schemas import ErrorResponse, ScrapeRequest, ScrapeResponse
from app.scraper.browser import BrowserError, fetch_page
from app.scraper.extractor import extract_product_data
from app.scraper.parser import parse_html

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Product URL Scraper",
    description="Accepts a product page URL and returns structured product data.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/scrape", response_model=ScrapeResponse, responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
async def scrape(request: ScrapeRequest):
    url = str(request.url)
    logger.info("Scraping URL: %s", url)

    if not settings.openrouter_api_key:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY is not configured")

    # 1. Fetch page with browser
    try:
        page_data = await fetch_page(url)
    except BrowserError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Browser error: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to load page: {e}")

    # 2. Parse HTML
    parsed = parse_html(page_data["html"], page_data["title"], url)

    # 3. Extract product data via LLM
    try:
        result = await extract_product_data(parsed, url)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error("Extraction error: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to extract product data: {e}")

    logger.info("Successfully scraped: %s", result.product_name)
    return result
