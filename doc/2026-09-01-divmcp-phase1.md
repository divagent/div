# divmcp — Phase 1 built & verified (2026-09-01)

Session record. Continue tomorrow. No commits made this session; `.env` stays
uncommitted in both `divcore` and `divmcp` (real secrets).

## Why divmcp exists

The backend agent's mission is the **hard-to-get leading signal** — grapevine /
小道消息 that a dividend may be cut, suspended, or raised **before** any official
declaration. Past/official facts are already handled by the frontend; the backend
just records them. The pain point is the un-official, not-easy-to-get hint.

Design principle we aligned on: **enumerate senses, not sources of truth.** Don't
hardcode which site has a fact (brittle if-else — one format change and it breaks).
Give the agent a general search + fetch backbone so it routes around any dead or
paywalled source. Redundancy of information = agent resilience + accuracy.

## What's built in `B:\divmcp`

A from-scratch MCP server (official `mcp` Python SDK, `FastMCP`, streamable-HTTP),
stateless so it fits a serverless host (FastAPI Cloud).

| File | Role |
|------|------|
| `divmcp/server.py` | `FastMCP` instance. `stateless_http=True`, `json_response=True`, `streamable_http_path="/"`. Mission instructions oriented to leading signals. |
| `divmcp/config.py` | Settings: `TAVILY_API_KEY` + `FETCH_TIMEOUT_SECONDS`/`FETCH_MAX_CHARS`. Placeholder-aware `tavily_ready`. `@lru_cache get_settings()`. |
| `divmcp/tools/__init__.py` | `register_all(mcp)` — explicit registry. Add Phase 2 tools here. |
| `divmcp/tools/search.py` | `web_search(query, max_results=6)` — Tavily advanced search. Fail-soft. |
| `divmcp/tools/fetch.py` | `fetch_url(url, max_chars=0)` — httpx (redirects, UA, timeout) + trafilatura markdown extraction, HTML-strip fallback. Fail-soft. |
| `main.py` | FastAPI `app`. Mounts MCP at `/mcp` (endpoint lands exactly at `/mcp`). `/health`. Lifespan runs `mcp.session_manager.run()`. |
| `README.md`, `.env.example` | docs + config template (old `DIVCORE_*` vars removed). |

Both tools **fail soft**: on missing key or any error they return `{error}` (+ empty
results) instead of raising, so the agent adjusts and continues.

## Verified (2026-09-01)

- `uv sync` installs cleanly (mcp 1.x, fastapi, httpx 0.28, trafilatura 2.2, tavily-python 0.8).
- App imports; routes resolve to exactly `/mcp` and `/health`; both tools register.
- `fetch_url` pulls a live page (example.com) → title + readable body.
- `web_search` fails soft with no key; with the real key returns spot-on hits — top
  result for "TELUS dividend cut 2026" was *"TU Slumps As Telus Slashes Dividend And
  Cuts 2026 Outlook"* (score 0.99). Exactly the leading signal we want to catch.

## Run locally

```bash
cd B:\divmcp
uv sync
cp .env.example .env   # add TAVILY_API_KEY (reuse the one in divcore/.env)
uv run fastapi dev main.py
# MCP:    http://127.0.0.1:8000/mcp
# health: http://127.0.0.1:8000/health
```

## Next (tomorrow)

1. **Deploy divmcp to FastAPI Cloud** — set `TAVILY_API_KEY` (and optional fetch
   limits) in its env.
2. **Agent tool-use loop in divcore** — the MCP client that bridges divmcp tools into
   Gemini function-calling so `gather_dividend_signals` / the predictor actually
   consume search+fetch. divcore = MCP client.
3. **Phase 2 tools in divmcp** — dedicated leading-signal senses: insider
   transactions (SEC Form 4 / SEDI), analyst actions, recent filings / transcripts.
   Register them in `divmcp/tools/__init__.py`.

## Standing constraints

- Never commit `.env` in either repo (Tavily, FMP, Finnhub, Alpha Vantage, Gemini,
  Google OAuth, DB creds). Don't echo secrets.
- The *declared number* must be retrieved deterministically (never hallucinated);
  the *judgment / leading read* is the LLM's job.
- Prior session record: `docs/2026-09-01-agent-truth-grounding.md`.
