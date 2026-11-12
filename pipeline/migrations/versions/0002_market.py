"""行情、指數、公司行動、法人資金流向

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "security",
        sa.Column("symbol", sa.String(16), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("market", sa.String(8), nullable=False, server_default="TWSE"),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("industry", sa.String(32), nullable=True),
        sa.Column("listed_on", sa.Date(), nullable=True),
        sa.Column("first_bar", sa.Date(), nullable=True),
        sa.Column("last_bar", sa.Date(), nullable=True),
        sa.Column("tracked", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "daily_bar",
        sa.Column("symbol", sa.String(16), primary_key=True),
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("open", sa.Float(), nullable=True),
        sa.Column("high", sa.Float(), nullable=True),
        sa.Column("low", sa.Float(), nullable=True),
        sa.Column("close", sa.Float(), nullable=True),
        sa.Column("change", sa.Float(), nullable=True),
        sa.Column("volume", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("value", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trades", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pe", sa.Float(), nullable=True),
    )
    op.create_index("ix_daily_bar_date", "daily_bar", ["date"])
    op.create_table(
        "index_bar",
        sa.Column("index_id", sa.String(64), primary_key=True),
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("change", sa.Float(), nullable=True),
        sa.Column("change_pct", sa.Float(), nullable=True),
    )
    op.create_table(
        "corporate_action",
        sa.Column("symbol", sa.String(16), primary_key=True),
        sa.Column("ex_date", sa.Date(), primary_key=True),
        sa.Column("type", sa.String(24), primary_key=True),
        sa.Column("prev_close", sa.Float(), nullable=False),
        sa.Column("ref_price", sa.Float(), nullable=False),
        sa.Column("factor", sa.Float(), nullable=False),
        sa.Column("affects_shares", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("source", sa.String(16), nullable=False),
    )
    op.create_table(
        "institutional_flow",
        sa.Column("symbol", sa.String(16), primary_key=True),
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("foreign_buy", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("foreign_sell", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("foreign_net", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trust_buy", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trust_sell", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trust_net", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dealer_net", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_net", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_institutional_flow_date", "institutional_flow", ["date"])
    op.create_table(
        "market_flow",
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("investor", sa.String(16), primary_key=True),
        sa.Column("buy", sa.Integer(), nullable=False),
        sa.Column("sell", sa.Integer(), nullable=False),
        sa.Column("net", sa.Integer(), nullable=False),
    )
    op.create_table(
        "foreign_holding",
        sa.Column("symbol", sa.String(16), primary_key=True),
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("shares_issued", sa.Integer(), nullable=False),
        sa.Column("foreign_shares", sa.Integer(), nullable=False),
        sa.Column("foreign_pct", sa.Float(), nullable=False),
        sa.Column("limit_pct", sa.Float(), nullable=True),
    )
    op.create_index("ix_foreign_holding_date", "foreign_holding", ["date"])


def downgrade() -> None:
    for t in ("foreign_holding", "market_flow", "institutional_flow", "corporate_action", "index_bar", "daily_bar", "security"):
        op.drop_table(t)
