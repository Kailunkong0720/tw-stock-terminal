"""corporate_action 加上當日漲跌停價

含現金增資的除權日，漲跌停不對稱（漲停以減除股利參考價、跌停以除權息參考價計算），
資料品質檢查要用報表給的實際漲跌停價。

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("corporate_action") as b:
        b.add_column(sa.Column("limit_up", sa.Float(), nullable=True))
        b.add_column(sa.Column("limit_down", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("corporate_action") as b:
        b.drop_column("limit_down")
        b.drop_column("limit_up")
