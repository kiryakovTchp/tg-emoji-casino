"""Add crash rounds and bets tables

Revision ID: 20250117_01_crash_tables
Revises: 20250116_05_referrals
Create Date: 2025-01-17 17:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20250117_01_crash_tables"
down_revision = "20250116_05_referrals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crash_rounds",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="betting"),
        sa.Column("seed", sa.String(length=128), nullable=False),
        sa.Column("seed_hash", sa.String(length=128), nullable=False),
        sa.Column("crash_point", sa.Numeric(10, 4)),
        sa.Column("bet_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("crash_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_crash_rounds_status", "crash_rounds", ["status"])

    op.create_table(
        "crash_bets",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("round_id", sa.BigInteger(), sa.ForeignKey("crash_rounds.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount_cash", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("amount_bonus", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("auto_cashout", sa.Numeric(10, 4)),
        sa.Column("cashout_multiplier", sa.Numeric(10, 4)),
        sa.Column("payout_cash", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("cashed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_crash_bets_round_user", "crash_bets", ["round_id", "user_id"])


def downgrade() -> None:
    op.drop_index("ix_crash_bets_round_user", table_name="crash_bets")
    op.drop_table("crash_bets")
    op.drop_index("ix_crash_rounds_status", table_name="crash_rounds")
    op.drop_table("crash_rounds")
