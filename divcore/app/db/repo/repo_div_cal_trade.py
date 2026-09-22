"""Repository for `div_cal_trade` — the calendar-tick + trade-log table.

Core-statement-on-`AsyncConnection` idiom (no ORM session; the connection's
`begin()` block commits). Rows are created when the user adds a calendar tick to
the Trades tab (`insert_tick`, idempotent on the `(symbol, ex_date)` unique
constraint); the Trades tab reads rows and patches the user-entered trade fields.
"""

from datetime import date
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.models.m_div import DivCalTrade

# Only these columns may be patched from the Trades tab. Everything else on the
# row is owned by the tick that seeded it.
EDITABLE_FIELDS = frozenset(
    {
        "company_name",
        "ex_date",  # exposed as the editable "ex-date"
        "payment_date",
        "quantity",
        "purchase_date",
        "purchase_amount",
        "sell_date",
        "sell_amount",
        "dividend_amount",
        "hidden",
    }
)


class DivCalTradeRepo:
    def __init__(self, db: AsyncConnection):
        self.db = db

    async def insert_tick(
        self,
        *,
        ticker: str,
        ex_date: Optional[str],
        amount: Optional[float] = None,
        divstatus: Optional[str] = None,
        confidence: Optional[float] = None,
        payment_date: Optional[str] = None,
        company_name: Optional[str] = None,
        google_event_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Ensure a calendar tick has a row so it shows in the Trades tab.

        Fills the tick-owned columns from the calendar event. Conflict target is
        `(symbol, ex_date)`: if the row already exists it is left untouched (so a
        user's trade entries are never clobbered) and returned as-is. Returns None
        if `ex_date` is missing (nothing to key on)."""
        ex: Optional[date] = date.fromisoformat(ex_date) if ex_date else None
        if ex is None:
            return None

        # Payment date is best-effort calendar data — ignore it if unparseable
        # rather than failing the insert.
        pay: Optional[date] = None
        if payment_date:
            try:
                pay = date.fromisoformat(str(payment_date)[:10])
            except ValueError:
                pay = None

        values = {
            "ticker": ticker,
            "ex_date": ex,
            "amount": amount,
            "divstatus": divstatus,
            "confidence": confidence,
            "payment_date": pay,
            "company_name": company_name,
            "google_event_id": google_event_id,
        }
        stmt = (
            insert(DivCalTrade)
            .values(values)
            .on_conflict_do_nothing(constraint="uq_div_cal_trade_symbol_ex_date")
            .returning(DivCalTrade.__table__)
        )
        row = (await self.db.execute(stmt)).mappings().first()
        if row:
            return dict(row)

        # Already existed (conflict → no row returned): fetch and return it intact.
        existing = (
            await self.db.execute(
                select(DivCalTrade.__table__).where(
                    DivCalTrade.ticker == ticker, DivCalTrade.ex_date == ex
                )
            )
        ).mappings().first()
        return dict(existing) if existing else None

    async def list_trades(self, *, include_hidden: bool = False) -> list[dict[str, Any]]:
        """Return every tick/trade row, newest ex-date first. Hidden rows are
        excluded unless `include_hidden` is True."""
        stmt = select(DivCalTrade.__table__)
        if not include_hidden:
            stmt = stmt.where(DivCalTrade.hidden.is_(False))
        stmt = stmt.order_by(DivCalTrade.ex_date.desc().nullslast())
        result = await self.db.execute(stmt)
        return [dict(row) for row in result.mappings().all()]

    async def update_trade(self, row_id: Any, fields: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Patch the user-editable columns of one row. Unknown keys are ignored.
        Returns the updated row, or None if the id doesn't exist / nothing valid
        was supplied."""
        clean = {k: v for k, v in fields.items() if k in EDITABLE_FIELDS}
        if not clean:
            return None
        stmt = (
            update(DivCalTrade)
            .where(DivCalTrade.id == row_id)
            .values(**clean)
            .returning(DivCalTrade.__table__)
        )
        result = await self.db.execute(stmt)
        row = result.mappings().first()
        return dict(row) if row else None
