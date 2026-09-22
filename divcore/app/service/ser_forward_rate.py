"""Same-day forward-yield refresh for the calendar list.

The homepage "Forward Rate" column is the forward dividend yield (%) priced at
the LATEST price (`regularMarketPrice` — live when the market's open, else the
last close; the same basis as the predict path's `facts.price`). The Google
Calendar event is the cache: each event carries forwardRate / forwardYield /
price / priceAsOf in its private props.

`enrich_forward_rates` is the lazy refresh: for every symbol on the list whose
cached value isn't from today, the first viewer of the day fetches Yahoo once,
computes the yield, patches it back onto the events, and returns it. A second
viewer that day finds priceAsOf == today already stamped and does zero fetches
(publish-time writes also stamp priceAsOf == today, so freshly predicted symbols
are skipped too). All best-effort — Yahoo/Calendar hiccups just leave "—".
"""

from __future__ import annotations

import asyncio
from datetime import date

import httpx

from app.adapters import gcal_api
from app.adapters.yahoo_price import forward_yield_latest
from app.core.ai_logging import log_event

_FIELDS = ("forwardRate", "forwardYield", "price", "priceAsOf")
_YAHOO_TIMEOUT = 8.0


def _apply(item: dict, payload: dict) -> None:
    for k in _FIELDS:
        item[k] = payload.get(k)


async def enrich_forward_rates(items: list[dict], *, trace_id: str = "internal") -> list[dict]:
    """Fill forward-yield fields on each calendar item, refreshing stale symbols.

    Mutates and returns `items` (list of flat event dicts from list_events).
    """
    if not items:
        return items

    today = date.today().isoformat()

    # Group items by ticker, and find any already-fresh (today) cache per ticker.
    by_ticker: dict[str, list[dict]] = {}
    fresh: dict[str, dict] = {}
    for it in items:
        tk = (it.get("ticker") or "").upper()
        if not tk:
            continue
        by_ticker.setdefault(tk, []).append(it)
        if it.get("priceAsOf") == today and it.get("forwardYield") is not None:
            fresh.setdefault(tk, {k: it.get(k) for k in _FIELDS})

    # Reuse today's cached value across every item of an already-fresh ticker.
    for tk, payload in fresh.items():
        for it in by_ticker[tk]:
            _apply(it, payload)

    stale = [tk for tk in by_ticker if tk not in fresh]
    if not stale:
        return items

    # Fetch the stale tickers once each, concurrently.
    async with httpx.AsyncClient(timeout=_YAHOO_TIMEOUT) as client:
        payloads = await asyncio.gather(
            *(forward_yield_latest(client, tk, trace_id=trace_id) for tk in stale)
        )

    # Apply + persist (write-back) for the ones that resolved.
    patch_jobs = []
    refreshed = 0
    for tk, payload in zip(stale, payloads):
        if not payload:
            continue
        refreshed += 1
        for it in by_ticker[tk]:
            _apply(it, payload)
            patch_jobs.append(
                asyncio.to_thread(
                    gcal_api.patch_private,
                    ticker=tk,
                    ex_date=it["exDate"],
                    updates={k: payload[k] for k in _FIELDS if payload.get(k) is not None},
                    trace_id=trace_id,
                )
            )

    if patch_jobs:
        # Best-effort cache write; a failed patch just means we recompute next load.
        await asyncio.gather(*patch_jobs, return_exceptions=True)

    log_event(
        "forward_rate_enrich_done",
        trace_id=trace_id,
        tickers=len(by_ticker),
        refreshed=refreshed,
        reused=len(fresh),
    )
    return items
