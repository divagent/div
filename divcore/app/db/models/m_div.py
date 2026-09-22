from datetime import date
from decimal import Decimal
import uuid
from typing import Optional, Dict, Any, List, TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Boolean, Column, ForeignKey, Index, String, Integer, Date, Numeric, Text, Float, UniqueConstraint

from app.db.models.m_base import Base, BaseMixin

class Div(Base, BaseMixin):
    __tablename__ = "dividends"
    
    company_name: Mapped[str] = mapped_column(String(255), nullable=True, index=True)
    symbol:       Mapped[str] = mapped_column(String(50), nullable=True, index=True,unique=True)

    dividend_ex_date: Mapped[date] = mapped_column(Date,nullable=True,index=True,)
    record_date: Mapped[date] = mapped_column(Date,nullable=True,)
    payment_date: Mapped[date] = mapped_column(Date,nullable=True,)
    dividend_rate: Mapped[Decimal] = mapped_column(Numeric(10, 4),nullable=True,)
    indicated_annual_dividend: Mapped[Decimal] = mapped_column(Numeric(10, 4),nullable=True,)
    announcement_date: Mapped[date] = mapped_column(Date,nullable=True,)
    
    # from finnhub
    latest_price: Mapped[Decimal] = mapped_column(Numeric(10, 4),nullable=True,)
    yield_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2),nullable=True,)
    market_cap: Mapped[Decimal] = mapped_column(Numeric(20, 2),nullable=True,)
    
    div_type:   Mapped[str] = mapped_column(String(255), nullable=True, index=True)
    company_type:   Mapped[str] = mapped_column(String(255), nullable=True, index=True)


class DivCalTrade(Base, BaseMixin):
    """One row per (symbol, ex-date) calendar tick, plus the user's trade log.

    Started life as `dividend_predictions` — the AI-predicted next dividend for a
    symbol. It now doubles as the backing store for the Trades tab: the prediction
    fields are written by the predict/publish flow, and the trade-entry fields
    (purchase/sell/dividend, total dollars) are filled in by the user. One row per
    tick, upserted on (symbol, ex_date); never purged.
    """
    __tablename__ = "div_cal_trade"

    # -- prediction / tick identity (written by the predict flow) -------------
    ticker:            Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    ex_date:           Mapped[date] = mapped_column(Date, nullable=True, index=True)
    amount:            Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=True)
    divstatus:         Mapped[str] = mapped_column(String(20), nullable=True)  # Declared|Prediction
    direction:         Mapped[str] = mapped_column(String(20), nullable=True)  # up|down|constant
    confidence:        Mapped[float] = mapped_column(Float, nullable=True)     # high|low as float score
    reasoning:         Mapped[str] = mapped_column(Text, nullable=True)
    sources:           Mapped[str] = mapped_column(Text, nullable=True)        # JSON-encoded list
    google_event_id:   Mapped[str] = mapped_column(String(255), nullable=True, index=True)

    # -- trade log (user-entered; total dollars) ------------------------------
    company_name:    Mapped[str] = mapped_column(String(255), nullable=True)
    payment_date:    Mapped[date] = mapped_column(Date, nullable=True)
    quantity:        Mapped[int] = mapped_column(Integer, nullable=True)
    purchase_date:   Mapped[date] = mapped_column(Date, nullable=True)
    purchase_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=True)
    sell_date:       Mapped[date] = mapped_column(Date, nullable=True)
    sell_amount:     Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=True)
    dividend_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=True)
    hidden:          Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    __table_args__ = (
        UniqueConstraint("ticker", "ex_date", name="uq_div_cal_trade_symbol_ex_date"),
    )



class DivChunkBase(Base, BaseMixin):
    __abstract__ = True

    div_id: Mapped[uuid.UUID] = mapped_column(nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=True)
    content: Mapped[str] = mapped_column(String, nullable=True)




class DivChunk1536(DivChunkBase):
    __tablename__ = "dividend_chunks_1536"

    embedding: Mapped[Optional[List[float]]] = mapped_column(
        Vector(1536),
        nullable=True,
    )
    __table_args__ = (
        Index(
            "ix_dividend_chunks_1536_div_chunk",
            "div_id",
            "chunk_index",
            unique=True,
        ),
    )


class DivChunk768(DivChunkBase):
    __tablename__ = "dividend_chunks_768"

    embedding: Mapped[Optional[List[float]]] = mapped_column(
        Vector(768),
        nullable=True,
    )
    __table_args__ = (
        Index(
            "ix_dividend_chunks_768_div_chunk",
            "div_id",
            "chunk_index",
            unique=True,
        ),
    )


class DivChunk3072(DivChunkBase):
    __tablename__ = "dividend_chunks_3072"

    embedding: Mapped[Optional[List[float]]] = mapped_column(
        Vector(3072),
        nullable=True,
    )
    __table_args__ = (
        Index(
            "ix_dividend_chunks_3072_div_chunk",
            "div_id",
            "chunk_index",
            unique=True,
        ),
    )
