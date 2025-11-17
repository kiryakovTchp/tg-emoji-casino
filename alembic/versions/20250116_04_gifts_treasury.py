"""gifts and treasury

Revision ID: 20250116_04
Revises: 20250116_03
Create Date: 2025-11-16 19:40:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20250116_04"
down_revision = "20250116_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

    op.create_table(
        "gifts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tier", sa.String(length=16), nullable=False),
        sa.Column("bonus_cost", sa.BigInteger(), nullable=False),
        sa.Column("xtr_cost", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("fulfilled_at", sa.DateTime(timezone=True)),
        sa.Column("metadata", json_type),
    )
    op.create_table(
        "treasury_state",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("current_xtr", sa.BigInteger(), nullable=False),
        sa.Column("gift_liability", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("budget_spent_date", sa.DateTime(timezone=True)),
        sa.Column("budget_spent_xtr", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("treasury_state")
    op.drop_table("gifts")
