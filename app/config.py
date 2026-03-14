from functools import lru_cache
from pydantic_settings import BaseSettings
import json


class Settings(BaseSettings):
    DATABASE_URL: str
    LLM_API_KEYS: list[str] = []
    # No default — startup will raise a clear error if this is not set in .env
    ADMIN_SECRET_KEY: str
    # True = auto-create unknown teams (dev/open mode)
    # False = only pre-seeded teams can play (event mode)
    ALLOW_UNKNOWN_TEAMS: bool = True

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
