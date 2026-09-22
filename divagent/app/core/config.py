from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Aiven Postgres connection strings (postgresql+asyncpg://...)
    DIV_AIVEN_ADMIN: str
    DIV_AIVEN_RLS: str | None = None

    GEMINI_API_KEY: str | None = None

    # Model the analyze agent runs on (M2: a single model; M3 makes this a ring).
    AGENT_GEMINI_MODEL: str = "gemini-3.6-flash"

    # divmcp — the MCP server that hosts the agent's tools (dividend_tracker,
    # web_search, fetch_url). The agent DISCOVERS tools here; it never imports them.
    # Local dev points at a locally-run divmcp; prod points at the hosted URL.
    DIVMCP_URL: str = "http://127.0.0.1:8000/mcp"

    # Polygon.io API key — used to fetch the previous trading day's close for
    # the whole US stock universe in one grouped-daily call (market cap enrich).
    POLYGON_API_KEY: str | None = None

    # Shared trace secret. divagent is agents-only and not browser-facing — only
    # divcore calls the trace endpoint, forwarding the same `X-Trace-Secret` the
    # frontend sent. Same TRACE_SECRET value across frontend build / divcore /
    # divagent. A miss 404s; unset disables the endpoint.
    TRACE_SECRET: str | None = None

    # App database URL used at runtime (admin: needs DDL via migrations + writes).
    @property
    def database_url(self) -> str:
        return self.DIV_AIVEN_ADMIN


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
