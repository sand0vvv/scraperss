from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openrouter_api_key: str = ""
    browser_timeout: int = 30000
    llm_model: str = "google/gemini-3-flash-preview"
    llm_max_tokens: int = 4096
    host: str = "0.0.0.0"
    port: int = 8080

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
