from datetime import date, datetime

from sqlalchemy import BigInteger, DateTime, Date, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Edgar(Base):
    """SEC EDGAR ticker↔exchange mapping (source: company_tickers_exchange.json),
    enriched with market cap.

    Holds only NYSE + Nasdaq rows. The spine (ticker/cik/name/exchange) comes from
    company_tickers_exchange.json; the market-cap columns are filled by a separate,
    manual enrich pass (shares from EDGAR XBRL, price from Polygon). This table is
    refreshed roughly twice a year, so the enrich columns are a plain snapshot
    (overwritten each run), not a history log.
    """

    __tablename__ = "edgar"

    ticker: Mapped[str] = mapped_column(String, primary_key=True)
    cik: Mapped[int] = mapped_column(BigInteger)
    name: Mapped[str | None] = mapped_column(String)
    exchange: Mapped[str | None] = mapped_column(String)

    # --- market-cap enrich (per manual /edgar/enrich run) ---
    # Shares from EDGAR XBRL dei:EntityCommonStockSharesOutstanding (per CIK).
    shares_outstanding: Mapped[int | None] = mapped_column(BigInteger)
    shares_as_of: Mapped[date | None] = mapped_column(Date)
    # Previous trading day's close from Polygon grouped-daily (per ticker).
    close_price: Mapped[float | None] = mapped_column(Numeric(20, 4))
    close_date: Mapped[date | None] = mapped_column(Date)
    # market_cap = shares_outstanding * close_price (whole USD).
    market_cap: Mapped[int | None] = mapped_column(BigInteger)
    enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
