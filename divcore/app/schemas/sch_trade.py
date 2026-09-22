"""Wire schemas for the Trades tab (`/div_trade/*`).

One row per (symbol, ex-date) calendar tick, backed by `div_cal_trade`. Amounts
are TOTAL DOLLARS (not per-share), so profit is a plain sum. camelCase field names
match the JSON the browser expects.
"""

from datetime import date
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field


def _iso(d: Any) -> Optional[str]:
    return d.isoformat() if isinstance(d, date) else (d or None)


def _f(v: Any) -> Optional[float]:
    return float(v) if v is not None else None


class TradeRow(BaseModel):
    id: str
    ticker: str
    name: Optional[str] = None
    # Firmness of the underlying tick (from the calendar): Declared vs Prediction.
    divstatus: Optional[str] = None
    # The tick's dividend amount (per share) carried from the calendar event.
    amount: Optional[float] = None
    exDate: Optional[str] = None
    paymentDate: Optional[str] = None
    quantity: Optional[int] = None
    purchaseDate: Optional[str] = None
    purchaseAmount: Optional[float] = None
    sellDate: Optional[str] = None
    sellAmount: Optional[float] = None
    dividendAmount: Optional[float] = None
    # Derived, never stored: proceeds - cost + dividends. Null while the position
    # is still open (not sold) or before a purchase is recorded.
    profit: Optional[float] = None
    status: Literal["open", "closed", "untraded"] = "untraded"
    hidden: bool = False

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "TradeRow":
        purchase = _f(row.get("purchase_amount"))
        sell = _f(row.get("sell_amount"))
        dividend = _f(row.get("dividend_amount"))

        if purchase is None and sell is None:
            status: str = "untraded"
        elif sell is not None:
            status = "closed"
        else:
            status = "open"

        # Realized P/L only once the position is closed; a bare dividend on an
        # open position isn't a settled profit, so leave it null until sold.
        profit = None
        if status == "closed":
            profit = round(sell - (purchase or 0.0) + (dividend or 0.0), 2)

        return cls(
            id=str(row["id"]),
            ticker=row.get("ticker") or "",
            name=row.get("company_name"),
            divstatus=row.get("divstatus"),
            amount=_f(row.get("amount")),
            exDate=_iso(row.get("ex_date")),
            paymentDate=_iso(row.get("payment_date")),
            quantity=int(row["quantity"]) if row.get("quantity") is not None else None,
            purchaseDate=_iso(row.get("purchase_date")),
            purchaseAmount=purchase,
            sellDate=_iso(row.get("sell_date")),
            sellAmount=sell,
            dividendAmount=dividend,
            profit=profit,
            status=status,  # type: ignore[arg-type]
            hidden=bool(row.get("hidden")),
        )


class TradeListResponse(BaseModel):
    items: List[TradeRow] = Field(default_factory=list)


class TradeInsert(BaseModel):
    """Body for adding a calendar tick to the Trades tab. Carries as much as the
    calendar event has; the trade-log fields start empty for the user to fill in."""
    ticker: str
    exDate: str
    amount: Optional[float] = None
    divstatus: Optional[str] = None
    confidence: Optional[float] = None
    paymentDate: Optional[str] = None
    companyName: Optional[str] = None
    googleEventId: Optional[str] = None


class TradeUpdate(BaseModel):
    """PATCH body — every field optional; only the ones sent are changed.

    `name`/`exDate`/`paymentDate` map to the tick's own columns (editable per the
    'make ex-date and payment-date editable' fallback); the rest are the trade log.
    """
    name: Optional[str] = None
    exDate: Optional[str] = None
    paymentDate: Optional[str] = None
    quantity: Optional[int] = None
    purchaseDate: Optional[str] = None
    purchaseAmount: Optional[float] = None
    sellDate: Optional[str] = None
    sellAmount: Optional[float] = None
    dividendAmount: Optional[float] = None
    hidden: Optional[bool] = None

    def to_columns(self) -> dict[str, Any]:
        """Map the camelCase patch to `div_cal_trade` columns, parsing dates.

        Only keys explicitly sent by the client are included, so an omitted field
        is left untouched while an explicit null clears the column.
        """
        sent = self.model_dump(exclude_unset=True)
        mapping = {
            "name": "company_name",
            "exDate": "ex_date",
            "paymentDate": "payment_date",
            "quantity": "quantity",
            "purchaseDate": "purchase_date",
            "purchaseAmount": "purchase_amount",
            "sellDate": "sell_date",
            "sellAmount": "sell_amount",
            "dividendAmount": "dividend_amount",
            "hidden": "hidden",
        }
        date_fields = {"exDate", "paymentDate", "purchaseDate", "sellDate"}
        out: dict[str, Any] = {}
        for key, col in mapping.items():
            if key not in sent:
                continue
            val = sent[key]
            if key in date_fields and val:
                val = date.fromisoformat(str(val)[:10])
            out[col] = val
        return out
