"""分析執行紀錄：每一項分析什麼時候跑、用了哪段資料、用什麼參數（網站「分析說明」的來源）。"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from pipeline.models.base import Base


class AnalysisRun(Base):
    __tablename__ = "analysis_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    step: Mapped[str] = mapped_column(String(32), index=True)  # factor / attribution / graph / news …
    started_at: Mapped[str] = mapped_column(String(40))  # ISO 8601，含時區（台北）
    finished_at: Mapped[str] = mapped_column(String(40))
    data_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    params: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON 物件
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
