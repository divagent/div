# app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional
from functools import lru_cache


class _Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env",env_file_encoding="utf-8",extra="ignore",)
    # Settings must not be instantiated directly.
    # Always use get_settings_singleton() to access application configuration.
    #     Settings 是实现细节，不是公共 API
    # 公共 API 只有 get_settings_singleton()
    GOOGLE_SHEET_URL: str= "https://docs.google.com/spreadsheets/d/15QBf76ab4zSt-S-oGSrSpgdJngpdGCxFMJqZkC6_sAM/export?format=csv"
    NASDAQ_URL: str= "https://api.nasdaq.com/api/calendar/dividends"

    GOOGLE_PROJECT_ID: str = "divcalendar-507102"
    
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_API_KEY_OPHIR: Optional[str] = None

    # Groq — free, fast, OpenAI-compatible. No key => Groq models are skipped.
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL_ID: str = "openai/gpt-oss-120b"

    # Mistral — official SDK. No key => Mistral models are skipped.
    MISTRAL_API_KEY: Optional[str] = None
    MISTRAL_MODEL_ID: str = "mistral-medium-latest"

    # Cloudflare Workers AI — OpenAI-compatible chat endpoint. Needs BOTH the API
    # token and the account id (the account id is part of the URL); missing either
    # => Cloudflare models are skipped.
    CLOUDFLARE_API_TOKEN: Optional[str] = None
    CLOUDFLARE_ACCOUNT_ID: Optional[str] = None
    CLOUDFLARE_MODEL_ID: str = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"

    # NVIDIA NIM — OpenAI-compatible endpoint at integrate.api.nvidia.com. No key =>
    # NVIDIA models are skipped.
    NVIDIA_API_KEY: Optional[str] = None
    NVIDIA_MODEL_ID: str = "nvidia/nemotron-3.5-lightning-30b-a3b"
    # The AI model rotation ring (hard round-robin). Every LLM call uses the NEXT
    # model and advances one shared global cursor, so consecutive calls never hit
    # the same model. Extend this list (to any length) to add models. Each entry is
    # "provider:model_id"; supported providers: "gemini", "groq". A model whose
    # provider has no API key is skipped.
    AI_ROTATION_MODELS: List[str] = [
        "groq:openai/gpt-oss-120b",
        "mistral:mistral-medium-latest",
        "cloudflare:@cf/meta/llama-3.3-70b-instruct-fp8-fast",
        "nvidia:nvidia/nemotron-3.5-lightning-30b-a3b",
    ]

    SERPERDEV_API_KEY: Optional[str] = None
    TAVILY_API_KEY: str = "ff"
    ALPHAVANTAGE_API_KEY:  str = "ff"
    EOD_API_KEY:  str = "ff"
    FINNHUB_API_KEY:  str = "ff"
    FMP_API_KEY: str = "ff"  # Financial Modeling Prep — declared dividends + payout/FCF

    # Google Calendar (predicted-dividend publishing) — see followup.md
    GOOGLE_OAUTH_CLIENT_ID: Optional[str] = "590057077351-seft0saimg261h13i3o8us7cpam5bkc8.apps.googleusercontent.com"
    GOOGLE_OAUTH_CLIENT_SECRET: Optional[str] = None
    GOOGLE_OAUTH_REFRESH_TOKEN: Optional[str] = None
    GOOGLE_CALENDAR_ID: Optional[str] = None
    # IANA timezone for published events. Events are timed 08:00–09:00 in this tz.
    CALENDAR_TZ: str = "America/Toronto"

    # Database
    DIV_AIVEN_ADMIN: str = "postgresql+asyncpg://username:pwd@local/icedb"
    DIV_AIVEN_RLS: str = "postgresql+asyncpg://username:pwd@local/icedb"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_ECHO: bool = False


    # Seed Data
    SEED_DATA: bool = True  # Whether to seed data on startup
    SEED_TYPE: str = "full"  # 'full', 'test', or 'none'
    SEED_SAMPLE_SIZE: int = 10  # Number of sample records to create
    
    ADMIN_PASSWORD: str = "admin123"  # Default admin password for seeding (change in production)

    # Application
    PROJECT_NAME: str = "Dividend - FA Cloud"
    VERSION: str = "26.2.11"
    DESCRIPTION: str = "Dividend investing, systematically enhanced."
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Security
    SECRET_KEY: str = "your-secret-key-here-change-in-production"

    # divagent (agents-only service) — divcore proxies agent runs to it. One shared
    # TRACE_SECRET gates the whole chain: the frontend sends it as X-Trace-Secret,
    # divcore validates it and forwards the SAME header on to divagent.
    DIVAGENT_URL: str = "http://localhost:8001"
    TRACE_SECRET: Optional[str] = None


@lru_cache()
def get_settings_singleton()-> _Settings:
    return _Settings()
