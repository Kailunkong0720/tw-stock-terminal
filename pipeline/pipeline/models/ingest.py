"""抓取紀錄：讓回補可以中斷後續跑。每個（來源, 鍵）一列，鍵通常是日期。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from pipeline.models.base import Base


class IngestLog(Base):
    __tablename__ = "ingest_log"

    source: Mapped[str] = mapped_column(String(64), primary_key=True)
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    # ok：成功且有資料；empty：成功但該日無資料（例如休市）；error：失敗待重試
    status: Mapped[str] = mapped_column(String(16))
    rows: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
