import asyncio
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Edgar
from app.services.upsert import bulk_upsert
from app.utils.edgar import (
    fetch_company_tickers_exchange,
    fetch_shares_outstanding,
    _HEADERS,
)
from app.utils.polygon import fetch_previous_closes

# EDGAR exchange labels we keep. NYSE American / Arca / OTC / CBOE are excluded.
KEEP_EXCHANGES = {"Nasdaq", "NYSE"}

# Stay well under SEC's ~10 req/sec courtesy limit while sweeping one call per
# CIK. A global spacer paces request *starts*; concurrency just covers latency.
_SEC_CONCURRENCY = 5
_SEC_MIN_INTERVAL = 0.13  # ~7-8 req/s
_SEC_MAX_RETRIES = 4


async def load_edgar(session: AsyncSession) -> dict[str, int]:
    """Fetch company_tickers_exchange.json, keep NYSE + Nasdaq rows, and upsert
    them into the `edgar` table.

    Returns a per-exchange row count.
    """
    rows = await fetch_company_tickers_exchange()

    values = []
    counts = {"Nasdaq": 0, "NYSE": 0}
    for r in rows:
        ticker = r.get("ticker")
        exchange = r.get("exchange")
        if not ticker or exchange not in KEEP_EXCHANGES:
            continue
        values.append(
            {
                "ticker": ticker,
                "cik": r.get("cik"),
                "name": r.get("name"),
                "exchange": exchange,
            }
        )
        counts[exchange] += 1

    async with session.begin():
        await bulk_upsert(session, Edgar, values)

    return counts


async def _shares_by_cik(ciks: list[int]) -> tuple[dict[int, tuple[int, object]], int]:
    """Fetch shares outstanding for each unique CIK, rate-limited for SEC.

    Returns ({cik: (shares, as_of)}, http_error_count). A global spacer keeps
    request starts ~`_SEC_MIN_INTERVAL` apart; 429s are retried with backoff.
    """
    sem = asyncio.Semaphore(_SEC_CONCURRENCY)
    pace = asyncio.Lock()
    next_at = 0.0  # monotonic time the next request may start
    out: dict[int, tuple[int, object]] = {}
    errors = 0

    async def wait_turn() -> None:
        nonlocal next_at
        async with pace:
            now = time.monotonic()
            if next_at > now:
                await asyncio.sleep(next_at - now)
            next_at = max(now, next_at) + _SEC_MIN_INTERVAL

    async with httpx.AsyncClient(timeout=30, headers=_HEADERS) as client:
        async def one(cik: int) -> None:
            nonlocal errors
            async with sem:
                for attempt in range(_SEC_MAX_RETRIES):
                    await wait_turn()
                    try:
                        res = await fetch_shares_outstanding(client, cik)
                        if res is not None:
                            out[cik] = res
                        return
                    except httpx.HTTPStatusError as e:
                        if e.response.status_code == 429 and attempt + 1 < _SEC_MAX_RETRIES:
                            await asyncio.sleep(1.0 * (attempt + 1))
                            continue
                        errors += 1
                        return
                    except (httpx.HTTPError, ValueError):
                        errors += 1
                        return

        await asyncio.gather(*(one(c) for c in ciks))

    return out, errors


def _price_for(ticker: str, closes: dict[str, float]) -> float | None:
    """Match an SEC ticker to a Polygon close. SEC uses '-' for share classes
    (BRK-B), Polygon uses '.' (BRK.B)."""
    if ticker in closes:
        return closes[ticker]
    return closes.get(ticker.replace("-", "."))


async def enrich_edgar(session: AsyncSession) -> dict[str, int]:
    """Fill the market-cap columns on `edgar`: shares from EDGAR XBRL (per CIK),
    previous close from Polygon (per ticker), and market_cap = shares * close.

    Manual, ~twice a year. Overwrites the enrich columns in place.
    """
    if not settings.POLYGON_API_KEY:
        raise RuntimeError("POLYGON_API_KEY is not set")

    rows = (await session.execute(select(Edgar.ticker, Edgar.cik))).all()
    # Release the implicit read transaction before the multi-minute network sweep.
    await session.commit()

    # Shares are per-CIK; fetch once per unique CIK and fan out to its tickers.
    shares, share_errors = await _shares_by_cik(sorted({cik for _, cik in rows}))
    closes, close_day = await fetch_previous_closes(settings.POLYGON_API_KEY)

    now = datetime.now(timezone.utc)
    values = []
    counts = {
        "total": len(rows),
        "with_shares": 0,
        "with_price": 0,
        "with_mktcap": 0,
        "share_fetch_errors": share_errors,
    }
    for ticker, cik in rows:
        sh = shares.get(cik)
        price = _price_for(ticker, closes)
        shares_val = sh[0] if sh else None
        market_cap = int(shares_val * price) if (shares_val and price) else None

        counts["with_shares"] += sh is not None
        counts["with_price"] += price is not None
        counts["with_mktcap"] += market_cap is not None

        values.append(
            {
                "ticker": ticker,
                "cik": cik,
                "shares_outstanding": shares_val,
                "shares_as_of": sh[1] if sh else None,
                "close_price": price,
                "close_date": close_day if price is not None else None,
                "market_cap": market_cap,
                "enriched_at": now,
            }
        )

    async with session.begin():
        await bulk_upsert(session, Edgar, values)

    return counts
