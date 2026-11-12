"""price_move：每日報酬的因子拆解與異常偵測

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "price_move",
        sa.Column("symbol", sa.String(16), primary_key=True),
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("ret", sa.Float(), nullable=False),  # 還原後報酬（與前一個有成交日比）
        sa.Column("gap", sa.Integer(), nullable=False),  # 與前一個有成交日之間隔了幾個交易日（1 = 連續）
        sa.Column("mkt", sa.Float(), nullable=True),  # 大盤貢獻
        sa.Column("sector", sa.Float(), nullable=True),  # 類股（相對大盤）貢獻
        sa.Column("overnight", sa.Float(), nullable=True),  # 前一晚費半貢獻
        sa.Column("idio", sa.Float(), nullable=True),  # 個股特有（殘差）
        sa.Column("z", sa.Float(), nullable=True),  # 殘差 ÷ 殘差標準差
        sa.Column("vol_ratio", sa.Float(), nullable=True),  # 成交量 ÷ 前 20 日均量
        sa.Column("anomaly", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_price_move_anomaly", "price_move", ["anomaly", "symbol"])


def downgrade() -> None:
    op.drop_table("price_move")
