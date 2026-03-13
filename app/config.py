from functools import lru_cache
from pydantic_settings import BaseSettings
import json


class Settings(BaseSettings):
    DATABASE_URL: str
    LLM_API_KEYS: list[str] = []
    ADMIN_SECRET_KEY: str = "default_admin_secret_please_change"

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
