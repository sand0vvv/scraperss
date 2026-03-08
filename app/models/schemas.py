from pydantic import BaseModel, HttpUrl


class ScrapeRequest(BaseModel):
    url: HttpUrl


class ScrapeResponse(BaseModel):
    product_name: str
    brand_name: str
    description: str
    key_benefits: list[str]
    price: str
    product_images: list[str]
    category: str
    raw_url: str

    # Optional fields
    target_audience: str | None = None
    ingredients: str | None = None
    specs: dict[str, str] | None = None
    price_original: str | None = None


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
