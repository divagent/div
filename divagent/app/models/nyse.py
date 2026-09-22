from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Nyse(Base):
    """NYSE-listed securities only (source: otherlisted.txt, Exchange == 'N')."""

    __tablename__ = "nyse"

    symbol: Mapped[str] = mapped_column("act_symbol", String, primary_key=True)
    security_name: Mapped[str | None] = mapped_column(String)
    exchange: Mapped[str | None] = mapped_column(String)
    cqs_symbol: Mapped[str | None] = mapped_column(String)
    etf: Mapped[bool] = mapped_column(Boolean, default=False)
    round_lot_size: Mapped[int | None] = mapped_column(Integer)
    test_issue: Mapped[bool] = mapped_column(Boolean, default=False)
    nasdaq_symbol: Mapped[str | None] = mapped_column(String)
