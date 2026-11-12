"""事件與歸因（PLAN.md 第 6 節）。"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from pipeline.models.base import Base


class Event(Base):
    __tablename__ = "event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uid: Mapped[str] = mapped_column(String(96), unique=True)
    symbol: Mapped[str | None] = mapped_column(String(16), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime)
    trade_date: Mapped[date] = mapped_column(Date)
    level: Mapped[str] = mapped_column(String(12))
    type: Mapped[str] = mapped_column(String(24))
    direction: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32))
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)


class Attribution(Base):
    __tablename__ = "attribution"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id", ondelete="CASCADE"), primary_key=True)
    rank: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    components: Mapped[str] = mapped_column(Text)
