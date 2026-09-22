from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Nasdaq(Base):
    """Securities listed on Nasdaq (source: nasdaqlisted.txt)."""

    __tablename__ = "nasdaq"

    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    security_name: Mapped[str | None] = mapped_column(String)
    market_category: Mapped[str | None] = mapped_column(String)
    test_issue: Mapped[bool] = mapped_column(Boolean, default=False)
    financial_status: Mapped[str | None] = mapped_column(String)
    round_lot_size: Mapped[int | None] = mapped_column(Integer)
    etf: Mapped[bool] = mapped_column(Boolean, default=False)
    next_shares: Mapped[bool] = mapped_column(Boolean, default=False)
