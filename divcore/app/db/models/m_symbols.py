from datetime import date
from decimal import Decimal
import uuid
from typing import Optional, Dict, Any, List, TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, ForeignKey, Index, String, Integer, Date, Numeric

from app.db.models.m_base import Base, BaseMixin

class Symbols(Base, BaseMixin):
    __tablename__ = "symbols"
    
    symbol: Mapped[str] = mapped_column(String, nullable=False, index=True, unique=True)
    symbol2: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String)
    displaySymbol: Mapped[str] = mapped_column(String)
    currency: Mapped[str] = mapped_column(String)

    figi: Mapped[str] = mapped_column(String)
    isin: Mapped[str] = mapped_column(String)
    mic: Mapped[str] = mapped_column(String)
    shareClassFIGI: Mapped[str] = mapped_column(String)

