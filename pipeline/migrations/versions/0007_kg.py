"""知識圖譜：節點與關係

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kg_node",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("type", sa.String(24), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("aliases", sa.Text(), nullable=True),  # JSON 陣列
        sa.Column("attrs", sa.Text(), nullable=True),  # JSON 物件
    )
    op.create_table(
        "kg_edge",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("src", sa.String(96), nullable=False),
        sa.Column("dst", sa.String(96), nullable=False),
        sa.Column("rel", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1"),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("source", sa.String(64), nullable=False),  # seed / data / official / llm
        sa.Column("note", sa.Text(), nullable=True),
    )
    op.create_index("ix_kg_edge_src", "kg_edge", ["src"])
    op.create_index("ix_kg_edge_dst", "kg_edge", ["dst"])


def downgrade() -> None:
    op.drop_table("kg_edge")
    op.drop_table("kg_node")
