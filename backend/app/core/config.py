from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    app_name: str = "Xeno AI Campaign Copilot"
    database_url: str = "sqlite:///./xeno.db"
    redis_url: str = "redis://localhost:6379/0"
    channel_simulator_url: str = "http://localhost:8100"
    jwt_secret: str = "dev-secret"
    api_prefix: str = "/api/v1"
    rate_limit_per_minute: int = 240

    # LLM provider configuration
    gemini_api_key: str = ""
    openai_api_key: str = ""
    llm_provider: str = "local"  # gemini | openai | local

    # Auth / security
    access_token_expire_minutes: int = 1440  # 24 hours

    # CORS
    cors_origins: str = "http://localhost:3000"

    # Webhook verification
    webhook_secret: str = "webhook-secret-change-me"


@lru_cache
def get_settings() -> Settings:
    return Settings()
