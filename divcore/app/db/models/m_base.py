# app/db/base.py
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, String, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func

class Base(DeclarativeBase): pass


class BaseMixin:
    id: Mapped[UUID] = mapped_column(Uuid,primary_key=True,default=uuid4, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    status: Mapped[str] = mapped_column(String, default="active", nullable=True)
    description: Mapped[str] = mapped_column(String,default="description",nullable=True)
