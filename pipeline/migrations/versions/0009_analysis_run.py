"""分析執行紀錄（網站「分析說明」：方法、時間、資料期間）

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analysis_run",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("step", sa.String(32), nullable=False),
        sa.Column("started_at", sa.String(40), nullable=False),
        sa.Column("finished_at", sa.String(40), nullable=False),
        sa.Column("data_from", sa.Date(), nullable=True),
        sa.Column("data_to", sa.Date(), nullable=True),
        sa.Column("params", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
    )
    op.create_index("ix_analysis_run_step", "analysis_run", ["step"])


def downgrade() -> None:
    op.drop_table("analysis_run")
