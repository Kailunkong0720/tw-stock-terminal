"""公司所在縣市（全球脈動頁把台股公司放在地圖上）

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("security") as batch:
        batch.add_column(sa.Column("city", sa.String(16), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("security") as batch:
        batch.drop_column("city")
