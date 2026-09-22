"""Market-briefing endpoint (internal).

`GET /api/v1/market/summary` runs the Strands market-briefing agent over the divmcp
tools and returns a structured `MarketBrief` (headline + narrative + real movers).
divagent is agents-only and not browser-facing — this is called by divcore, which
thin-forwards the browser's request and adds the shared secret.

Gated by the shared `X-Trace-Secret` header (TRACE_SECRET, forwarded by divcore).
A miss returns 404 so the endpoint's existence isn't confirmed to a prober.

Caching: the briefing is expensive (several live web calls + an LLM run) and only
needs to refresh ~hourly, so we keep the last result in a process-local cache with a
1-hour TTL and a lock so concurrent requests don't stampede the agent. On a
generation failure we serve the stale briefing if we have one, rather than 500.
"""

from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, Header, HTTPException

from app.agent.market import generate_brief
from app.core.config import settings
from app.schemas.market import MarketBrief

router = APIRouter(prefix="/market", tags=["market"])

_TTL_SECONDS = 3600.0
_lock = asyncio.Lock()
_cache: dict[str, object] = {"brief": None, "ts": 0.0}


def _fresh() -> MarketBrief | None:
    brief = _cache["brief"]
    if brief is not None and (time.monotonic() - float(_cache["ts"])) < _TTL_SECONDS:
        return brief  # type: ignore[return-value]
    return None


@router.get("/summary", response_model=MarketBrief)
async def market_summary(
    x_trace_secret: str | None = Header(default=None),
) -> MarketBrief:
    secret = settings.TRACE_SECRET
    if not secret or x_trace_secret != secret:
        raise HTTPException(status_code=404)

    cached = _fresh()
    if cached is not None:
        return cached

    async with _lock:
        # Re-check under the lock: a concurrent request may have just refreshed it.
        cached = _fresh()
        if cached is not None:
            return cached
        try:
            brief = await generate_brief()
        except Exception:
            stale = _cache["brief"]
            if stale is not None:
                return stale  # type: ignore[return-value]
            raise HTTPException(status_code=503, detail="market briefing unavailable")
        _cache["brief"] = brief
        _cache["ts"] = time.monotonic()
        return brief
