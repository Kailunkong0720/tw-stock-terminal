"""知識圖譜（PLAN.md 6.3）。圖存在兩張表，管線用 NetworkX 走訪，輸出成 JSON 子圖。"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from pipeline.models.base import Base


class KgNode(Base):
    __tablename__ = "kg_node"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    type: Mapped[str] = mapped_column(String(24))
    name: Mapped[str] = mapped_column(String(128))
    aliases: Mapped[str | None] = mapped_column(Text, nullable=True)
    attrs: Mapped[str | None] = mapped_column(Text, nullable=True)


class KgEdge(Base):
    __tablename__ = "kg_edge"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    src: Mapped[str] = mapped_column(String(96))
    dst: Mapped[str] = mapped_column(String(96))
    rel: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
