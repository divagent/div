from datetime import date, timedelta

import httpx

# Grouped daily bars: one call returns OHLC for every US stock on a given date.
# https://polygon.io/docs/stocks/get_v2_aggs_grouped_locale_us_market_stocks__date
GROUPED_DAILY_URL = (
    "https://api.polygon.io/v2/aggs/grouped/locale/us/market/stocks/{day}"
)


async def fetch_previous_closes(
    api_key: str, on: date | None = None, max_lookback: int = 5
) -> tuple[dict[str, float], date]:
    """Return ({ticker: close_price}, trading_day) for the most recent trading day.

    Polygon's grouped-daily endpoint returns an empty result set on weekends and
    market holidays, so we walk back from `on` (default: yesterday) up to
    `max_lookback` days until we hit a day with data.
    """
    start = (on or date.today() - timedelta(days=1))

    async with httpx.AsyncClient(timeout=60) as client:
        for i in range(max_lookback + 1):
            day = start - timedelta(days=i)
            resp = await client.get(
                GROUPED_DAILY_URL.format(day=day.isoformat()),
                params={"adjusted": "true", "apiKey": api_key},
            )
            resp.raise_for_status()
            results = resp.json().get("results") or []
            if results:
                closes = {
                    r["T"]: r["c"]
                    for r in results
                    if r.get("T") and r.get("c") is not None
                }
                return closes, day

    raise RuntimeError(
        f"No Polygon grouped-daily data in the {max_lookback} days before {start}"
    )
