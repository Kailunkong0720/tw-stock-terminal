"""事件與歸因

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "event",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("uid", sa.String(96), nullable=False, unique=True),  # 來源內的唯一鍵，重抓時用來去重
        sa.Column("symbol", sa.String(16), nullable=True),  # 市場層級事件為 NULL
        sa.Column("at", sa.DateTime(), nullable=False),  # 公告／發布時間（台北時間）
        sa.Column("trade_date", sa.Date(), nullable=False),  # 影響的交易日（盤後公告算下一個交易日）
        sa.Column("level", sa.String(12), nullable=False),  # official / media / market
        sa.Column("type", sa.String(24), nullable=False),
        sa.Column("direction", sa.Integer(), nullable=False, server_default="0"),  # +1 利多 / −1 利空 / 0 未知
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
    )
    op.create_index("ix_event_symbol_date", "event", ["symbol", "trade_date"])
    op.create_index("ix_event_date", "event", ["trade_date"])
    op.create_table(
        "attribution",
        sa.Column("symbol", sa.String(16), primary_key=True),
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("event.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("components", sa.Text(), nullable=False),  # JSON：各分項分數
    )


def downgrade() -> None:
    op.drop_table("attribution")
    op.drop_table("event")
