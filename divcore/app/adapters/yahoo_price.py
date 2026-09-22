"""Yahoo Finance price + dividend history, server-side (best-effort).

The frontend reads Yahoo's chart endpoint directly (through a CORS proxy) in
`ticker.ts` and sends the price as `facts.price` on the predict request, which is
the price the calendar's "Forward Rate" (forward yield %) is normally computed
against. This module is the server-side FALLBACK for the rare case where the
frontend couldn't reach Yahoo (empty `facts.price`): one chart call gives us the
latest price (`regularMarketPrice` — live when the market's open, else the last
close, matching `facts.price`'s meaning) plus the trailing dividend history.

Everything here is best-effort — Yahoo can rate-limit or block, so callers must
treat a ``None`` result as "unknown" and degrade gracefully (show "—"), never
500. A browser-ish User-Agent and a short timeout keep it polite.

`prev_close` (the last completed daily bar strictly before today) is also parsed
and exposed on the quote for callers that want a stable close basis, though the
default forward-yield path uses the latest price.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Sequence, Tuple

import httpx

from app.core.ai_logging import log_event

_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_UA = "Mozilla/5.0 (compatible; DivCore/1.0)"
_TIMEOUT = 8.0


class YahooQuote:
    """Flat holder for one symbol's price + trailing dividends."""

    __slots__ = ("ticker", "currency", "latest_price", "prev_close", "prev_close_date", "dividends")

    def __init__(
        self,
        ticker: str,
        currency: Optional[str],
        latest_price: Optional[float],
        prev_close: Optional[float],
        prev_close_date: Optional[str],
        dividends: List[Tuple[str, float]],
    ) -> None:
        self.ticker = ticker
        self.currency = currency
        self.latest_price = latest_price
        self.prev_close = prev_close
        self.prev_close_date = prev_close_date
        self.dividends = dividends


def forward_rate_and_yield(
    dividends: Sequence[Tuple[str, float]], price: Optional[float]
) -> Tuple[Optional[float], Optional[float]]:
    """Annualized forward dividend (latest amount × payments/year) and its yield %.

    Mirrors the frontend (`ticker.ts`) and `age_grounding`: the forward *rate* is
    a currency amount independent of price; the forward *yield* is that rate over
    the given price. Returns (forward_rate, forward_yield_pct); either may be None.
    """
    hist = sorted(
        [(d, float(a)) for d, a in dividends if d and a is not None],
        key=lambda x: x[0],
        reverse=True,  # newest first
    )
    n = len(hist)
    if not n:
        return None, None
    forward_rate = round(hist[0][1] * n, 4)
    if not price or price <= 0:
        return forward_rate, None
    return forward_rate, round(forward_rate / price * 100, 2)


def _parse_chart(ticker: str, payload: dict) -> Optional[YahooQuote]:
    result = ((payload or {}).get("chart") or {}).get("result") or []
    if not result:
        return None
    r = result[0]
    meta = r.get("meta") or {}

    timestamps: list[int] = r.get("timestamp") or []
    quote = ((r.get("indicators") or {}).get("quote") or [{}])[0]
    closes: list = quote.get("close") or []

    today = datetime.now(timezone.utc).date()
    prev_close: Optional[float] = None
    prev_close_date: Optional[str] = None
    # Walk newest→oldest; take the last completed bar strictly before today.
    for ts, close in zip(reversed(timestamps), reversed(closes)):
        if close is None:
            continue
        bar_date = datetime.fromtimestamp(ts, tz=timezone.utc).date()
        if bar_date < today:
            prev_close = round(float(close), 4)
            prev_close_date = bar_date.isoformat()
            break

    latest_price = meta.get("regularMarketPrice")
    if latest_price is None:
        # Fall back to the most recent non-null close (may be today's bar).
        for close in reversed(closes):
            if close is not None:
                latest_price = float(close)
                break
    latest_price = round(float(latest_price), 4) if latest_price is not None else None

    cutoff_ts = int(datetime(today.year - 1, today.month, today.day, tzinfo=timezone.utc).timestamp())
    raw_divs = ((r.get("events") or {}).get("dividends") or {})
    dividends: List[Tuple[str, float]] = []
    for ev in raw_divs.values():
        ev_ts = ev.get("date")
        amt = ev.get("amount")
        if ev_ts is None or amt is None or ev_ts < cutoff_ts:
            continue
        d = datetime.fromtimestamp(ev_ts, tz=timezone.utc).date().isoformat()
        dividends.append((d, float(amt)))

    return YahooQuote(
        ticker=(meta.get("symbol") or ticker).upper(),
        currency=meta.get("currency"),
        latest_price=latest_price,
        prev_close=prev_close,
        prev_close_date=prev_close_date,
        dividends=dividends,
    )


async def fetch_quote(
    client: httpx.AsyncClient, ticker: str, *, trace_id: str = "internal"
) -> Optional[YahooQuote]:
    """Fetch one ticker's price + trailing dividends. Returns None on any failure."""
    base = (ticker or "").strip().upper()
    if not base:
        return None
    try:
        r = await client.get(
            _CHART_URL.format(symbol=base),
            params={"range": "1y", "interval": "1d", "events": "div"},
            headers={"User-Agent": _UA},
        )
        if r.status_code != 200:
            return None
        return _parse_chart(base, r.json())
    except Exception as exc:  # best-effort: never propagate to the caller
        log_event(
            "yahoo_price_fetch_failure",
            trace_id=trace_id,
            ticker=base,
            severity="LOW",
            error=str(exc),
        )
        return None


async def forward_yield_latest(
    client: httpx.AsyncClient, ticker: str, *, trace_id: str = "internal"
) -> Optional[dict]:
    """Forward-yield cache payload for one ticker, priced at the LATEST price.

    Uses `regularMarketPrice` (live when the market's open, else the last close —
    the same basis as the frontend's `facts.price`), so priceAsOf is today.
    Returns forwardRate / forwardYield / price / priceAsOf, or None if
    price/history is unavailable.
    """
    from datetime import date

    quote = await fetch_quote(client, ticker, trace_id=trace_id)
    if quote is None or quote.latest_price is None:
        return None
    forward_rate, forward_yield = forward_rate_and_yield(quote.dividends, quote.latest_price)
    if forward_yield is None:
        return None
    return {
        "forwardRate": forward_rate,
        "forwardYield": forward_yield,
        "price": quote.latest_price,
        "priceAsOf": date.today().isoformat(),
    }
