from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings
import json


class Settings(BaseSettings):
    DATABASE_URL: str
    LLM_API_KEYS: list[str] | str = []
    
    @field_validator("LLM_API_KEYS", mode="before")
    def parse_api_keys(cls, v):
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [str(x) for x in parsed]
            except Exception:
                pass
            return [k.strip() for k in v.split(",") if k.strip()]
        return v
        
    # No default — startup will raise a clear error if this is not set in .env
    ADMIN_SECRET_KEY: str
    # CTFd admin credentials for server-side scoreboard sync.
    # Both must be set for flag solves to appear on the CTFd scoreboard.
    # If either is empty, sync is skipped gracefully.
    CTFD_ADMIN_EMAIL: str = ""
    CTFD_ADMIN_PASSWORD: str = ""
    # True = auto-create unknown teams (dev/open mode)
    # False = only pre-seeded teams can play (event mode)
    ALLOW_UNKNOWN_TEAMS: bool = True

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
