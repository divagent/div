"""Runtime configuration, sourced from environment / `.env`.

Deliberately tiny: the whole service needs one secret (the web-search key) and a
couple of safety limits. Keep it that way — new tools add their own keys here.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Values that mean "not really set" — treated as absent so the tool fails soft.
_PLACEHOLDERS = {"", "changeme", "none", "ff", "your-key-here"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # web_search — Tavily is the generic search "sense". Absent key => tool skips.
    TAVILY_API_KEY: str = ""

    # market_news — Exa is the market-news "sense" (semantic, recency-aware search
    # of the day's story). Absent key => the tool skips (fail-soft like the rest).
    EXA_API_KEY: str = ""

    # fetch_url safety limits.
    FETCH_TIMEOUT_SECONDS: float = 20.0
    FETCH_MAX_CHARS: int = 8000

    @property
    def tavily_ready(self) -> bool:
        return self.TAVILY_API_KEY.strip().lower() not in _PLACEHOLDERS

    @property
    def exa_ready(self) -> bool:
        return self.EXA_API_KEY.strip().lower() not in _PLACEHOLDERS


@lru_cache
def get_settings() -> Settings:
    return Settings()
