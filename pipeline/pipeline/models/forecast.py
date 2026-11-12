"""Kronos 預測結果（PLAN.md 第 5 節）。"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from pipeline.models.base import Base


class ForecastRun(Base):
    __tablename__ = "forecast_run"
    __table_args__ = (UniqueConstraint("symbol", "base_date", "kind", "model", name="uq_forecast_run"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16))
    base_date: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(12))
    model: Mapped[str] = mapped_column(String(32))
    lookback: Mapped[int] = mapped_column(Integer)
    pred_len: Mapped[int] = mapped_column(Integer)
    n_paths: Mapped[int] = mapped_column(Integer)
    base_close: Mapped[float] = mapped_column(Float)
    paths_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class ForecastStep(Base):
    __tablename__ = "forecast_step"

    run_id: Mapped[int] = mapped_column(ForeignKey("forecast_run.id", ondelete="CASCADE"), primary_key=True)
    step: Mapped[int] = mapped_column(Integer, primary_key=True)
    p05: Mapped[float] = mapped_column(Float)
    p10: Mapped[float] = mapped_column(Float)
    p25: Mapped[float] = mapped_column(Float)
    p50: Mapped[float] = mapped_column(Float)
    p75: Mapped[float] = mapped_column(Float)
    p90: Mapped[float] = mapped_column(Float)
    p95: Mapped[float] = mapped_column(Float)
    up_prob: Mapped[float] = mapped_column(Float)
    mdd_p50: Mapped[float] = mapped_column(Float)
