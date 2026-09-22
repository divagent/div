from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Nasdaq, Nyse
from app.utils.nasdaq_files import fetch_pipe_file, to_bool, to_int

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"


async def _bulk_upsert(session: AsyncSession, model, values: list[dict]) -> int:
    """Insert rows, updating existing ones on primary-key conflict.

    No deletes: symbols missing from the source (e.g. delisted) are left as-is.
    """
    if not values:
        return 0

    table = model.__table__
    pk_cols = {c.name for c in table.primary_key.columns}

    # Dedupe within the batch (last occurrence wins); ON CONFLICT cannot touch
    # the same row twice in one statement.
    deduped: dict[tuple, dict] = {}
    for row in values:
        deduped[tuple(row[c] for c in pk_cols)] = row
    values = list(deduped.values())

    stmt = pg_insert(table).values(values)
    update_cols = {
        c.name: getattr(stmt.excluded, c.name)
        for c in table.columns
        if c.name not in pk_cols
    }
    stmt = stmt.on_conflict_do_update(
        index_elements=list(pk_cols),
        set_=update_cols,
    )
    await session.execute(stmt)
    return len(values)


async def load_nasdaq(session: AsyncSession) -> int:
    """Fetch nasdaqlisted.txt and upsert into the `nasdaq` table."""
    rows = await fetch_pipe_file(NASDAQ_LISTED_URL)

    values = [
        {
            "symbol": r["Symbol"],
            "security_name": r.get("Security Name"),
            "market_category": r.get("Market Category"),
            "test_issue": to_bool(r.get("Test Issue")),
            "financial_status": r.get("Financial Status"),
            "round_lot_size": to_int(r.get("Round Lot Size")),
            "etf": to_bool(r.get("ETF")),
            "next_shares": to_bool(r.get("NextShares")),
        }
        for r in rows
        if r.get("Symbol")
    ]
    return await _bulk_upsert(session, Nasdaq, values)


async def load_nyse(session: AsyncSession) -> int:
    """Fetch otherlisted.txt, keep only NYSE rows (Exchange == 'N'), and
    upsert into the `nyse` table."""
    rows = await fetch_pipe_file(OTHER_LISTED_URL)

    values = [
        {
            "act_symbol": r["ACT Symbol"],
            "security_name": r.get("Security Name"),
            "exchange": r.get("Exchange"),
            "cqs_symbol": r.get("CQS Symbol"),
            "etf": to_bool(r.get("ETF")),
            "round_lot_size": to_int(r.get("Round Lot Size")),
            "test_issue": to_bool(r.get("Test Issue")),
            "nasdaq_symbol": r.get("NASDAQ Symbol"),
        }
        for r in rows
        if r.get("ACT Symbol") and (r.get("Exchange") or "").strip() == "N"
    ]
    return await _bulk_upsert(session, Nyse, values)


async def refresh_all(session: AsyncSession) -> tuple[int, int]:
    """Upsert both tables inside a single transaction."""
    async with session.begin():
        nasdaq_count = await load_nasdaq(session)
        nyse_count = await load_nyse(session)
    return nasdaq_count, nyse_count
