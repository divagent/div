"""Frontend-facing market-briefing forward (thin).

`GET /div_agent/market_summary` is the target of the idle right-pane market
snapshot in divreact. divcore is the only frontend-facing backend and does NOT run
the agent itself: it proxies to divagent's agents-only briefing endpoint, adding the
shared `X-Trace-Secret` (the same TRACE_SECRET across frontend / divcore / divagent)
so the browser never needs to hold that secret. It is already behind the app-level
admin Basic auth, so no extra gating is added here.

divagent owns the hourly cache; this forward is stateless.
"""

import httpx
from fastapi import APIRouter, HTTPException

from app.config import get_settings_singleton

marketRou = APIRouter()


@marketRou.get("/div_agent/market_summary", tags=["Agent"])
async def market_summary() -> dict:
    settings = get_settings_singleton()
    url = f"{settings.DIVAGENT_URL.rstrip('/')}/api/v1/market/summary"

    # The agent makes several live web calls plus an LLM run, so allow a generous
    # read budget while keeping the connect timeout short.
    timeout = httpx.Timeout(10.0, read=120.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                url, headers={"X-Trace-Secret": settings.TRACE_SECRET or ""}
            )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"divagent unreachable: {exc}")

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="market summary unavailable")
    return resp.json()
