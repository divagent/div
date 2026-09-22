from datetime import date

import httpx

COMPANY_TICKERS_EXCHANGE_URL = (
    "https://www.sec.gov/files/company_tickers_exchange.json"
)
COMPANY_CONCEPT_URL = (
    "https://data.sec.gov/api/xbrl/companyconcept/"
    "CIK{cik:010d}/dei/EntityCommonStockSharesOutstanding.json"
)

# SEC requires a descriptive User-Agent with contact info, else it returns 403.
_HEADERS = {"User-Agent": "divagent/0.1 (admin@divagent.local)"}


async def fetch_company_tickers_exchange() -> list[dict]:
    """Fetch SEC's company_tickers_exchange.json and return rows as dicts.

    The file has the shape {"fields": [...], "data": [[...], ...]}; this
    zips each data row against the field names.
    """
    async with httpx.AsyncClient(timeout=30, headers=_HEADERS) as client:
        resp = await client.get(COMPANY_TICKERS_EXCHANGE_URL)
        resp.raise_for_status()
        payload = resp.json()

    fields = payload.get("fields", [])
    return [dict(zip(fields, row)) for row in payload.get("data", [])]


async def fetch_shares_outstanding(
    client: httpx.AsyncClient, cik: int
) -> tuple[int, date] | None:
    """Return (shares, as_of_date) for a CIK from EDGAR XBRL, or None.

    Uses the dei:EntityCommonStockSharesOutstanding concept and picks the most
    recently reported value (latest period-end, breaking ties by filing date).
    Returns None when the company has no such fact (404) or an empty series.
    """
    resp = await client.get(COMPANY_CONCEPT_URL.format(cik=cik))
    if resp.status_code == 404:
        return None
    resp.raise_for_status()

    points = resp.json().get("units", {}).get("shares", [])
    if not points:
        return None

    latest = max(points, key=lambda p: (p.get("end", ""), p.get("filed", "")))
    val, end = latest.get("val"), latest.get("end")
    if val is None or not end:
        return None
    return int(val), date.fromisoformat(end)
