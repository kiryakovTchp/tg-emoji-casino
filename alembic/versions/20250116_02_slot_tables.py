"""slot tables

Revision ID: 20250116_02
Revises: 20250116_01
Create Date: 2025-11-16 18:40:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20250116_02"
down_revision = "20250116_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("props", json_type, nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="bot"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_events_user_id", "events", ["user_id"])
    op.create_index("ix_events_name", "events", ["name"])

    op.create_table(
        "spins",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bet_coins_cash", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("bet_coins_bonus", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("dice_value", sa.Integer(), nullable=False),
        sa.Column("symbols", json_type, nullable=False),
        sa.Column("multiplier", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("payout_cash", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("payout_bonus", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_spins_user_id", "spins", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_spins_user_id", table_name="spins")
    op.drop_table("spins")
    op.drop_index("ix_events_name", table_name="events")
    op.drop_index("ix_events_user_id", table_name="events")
    op.drop_table("events")
