"""Kronos 預測：每次執行與各步的分位數

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "forecast_run",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("base_date", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(12), nullable=False),  # latest / backtest
        sa.Column("model", sa.String(32), nullable=False),
        sa.Column("lookback", sa.Integer(), nullable=False),
        sa.Column("pred_len", sa.Integer(), nullable=False),
        sa.Column("n_paths", sa.Integer(), nullable=False),
        sa.Column("base_close", sa.Float(), nullable=False),  # 基準日的還原收盤（以基準日當下已知的公司行動計）
        sa.Column("paths_json", sa.Text(), nullable=True),  # 各條取樣路徑的收盤（只有 latest 保存）
        sa.Column("seconds", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("symbol", "base_date", "kind", "model", name="uq_forecast_run"),
    )
    op.create_index("ix_forecast_run_kind_date", "forecast_run", ["kind", "base_date"])
    op.create_table(
        "forecast_step",
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("forecast_run.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("step", sa.Integer(), primary_key=True),  # 第幾個交易日（1 起算）
        sa.Column("p05", sa.Float(), nullable=False),
        sa.Column("p10", sa.Float(), nullable=False),
        sa.Column("p25", sa.Float(), nullable=False),
        sa.Column("p50", sa.Float(), nullable=False),
        sa.Column("p75", sa.Float(), nullable=False),
        sa.Column("p90", sa.Float(), nullable=False),
        sa.Column("p95", sa.Float(), nullable=False),
        sa.Column("up_prob", sa.Float(), nullable=False),  # 收盤高於基準日收盤的路徑比例
        sa.Column("mdd_p50", sa.Float(), nullable=False),  # 到這一步為止最大回檔的中位數（負值）
    )


def downgrade() -> None:
    op.drop_table("forecast_step")
    op.drop_table("forecast_run")
