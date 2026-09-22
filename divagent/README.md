What divagent does

It's a FastAPI service that builds a database of US-listed stocks (NYSE + Nasdaq) with market-cap data — a data-loading backend, scaffolded via the FastAPI CLI and backed by Aiven Postgres (async SQLAlchemy + Alembic migrations). Despite the name, there's no "agent" logic yet — it's the data layer.

It exposes three POST endpoints (under /api/v1):

Symbols — /symbols/refresh
- Fetches Nasdaq Trader's directory files (nasdaqlisted.txt, otherlisted.txt), and upserts them into two tables: nasdaq (all rows) and nyse (only Exchange == 'N' rows). No deletes — delisted symbols are left in place.

EDGAR — /edgar/refresh and /edgar/enrich
- refresh: pulls SEC EDGAR's company_tickers_exchange.json, keeps only NYSE + Nasdaq rows, and upserts the ticker↔CIK↔name↔exchange "spine" into the edgar table.
- enrich: a manual, run-a-couple-times-a-year pass that fills in market cap:
  - shares outstanding from EDGAR XBRL (per CIK, rate-limited to stay under SEC's ~10 req/s courtesy limit),
  - previous day's close from Polygon.io (one grouped-daily call for the whole universe),
  - market_cap = shares × close.
  - Handles the ticker-notation mismatch between SEC (BRK-B) and Polygon (BRK.B).

Stack: FastAPI, SQLAlchemy 2.0 async + asyncpg, Alembic, pydantic-settings (config from .env), httpx. Requires DIV_AIVEN_ADMIN (Postgres URL) and POLYGON_API_KEY; a GEMINI_API_KEY slot exists in config but isn't used yet — likely hinting at the eventual "agent" purpose.

In short: an ingestion/ETL backend that keeps a Postgres table of NYSE/Nasdaq tickers enriched with market caps, ready to be queried (or, given the name and unused Gemini key, fed to an LLM agent later).