"""base schema

Revision ID: 20250116_01
Revises:
Create Date: 2025-11-16 17:36:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20250116_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tg_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("username", sa.String(length=64)),
        sa.Column("locale", sa.String(length=8)),
        sa.Column("banned", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_seen", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("first_deposit_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "wallets",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("coins_cash", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("coins_bonus", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("free_spins_left", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "bonus_awards",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("granted", sa.BigInteger(), nullable=False),
        sa.Column("wr_mult", sa.Numeric(6, 2), nullable=False),
        sa.Column("turnover_required", sa.BigInteger(), nullable=False),
        sa.Column("turnover_progress", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cap_cashout", sa.BigInteger(), nullable=False),
        sa.Column("cashed_out", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("unlocked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_bonus_awards_user_id", "bonus_awards", ["user_id"])

    op.create_table(
        "turnover_rules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("game", sa.String(length=32), nullable=False),
        sa.Column("contribution", sa.SmallInteger(), nullable=False, server_default="100"),
        sa.UniqueConstraint("game", name="uq_turnover_rules_game"),
    )

    op.create_table(
        "purchases",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("charge_id", sa.String(length=128), nullable=False),
        sa.Column("product_code", sa.String(length=64), nullable=False),
        sa.Column("amount_xtr", sa.Integer(), nullable=False),
        sa.Column("coins_granted", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("bonus_granted", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="completed"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("charge_id", name="uq_purchases_charge"),
    )

    op.create_table(
        "refunds",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("purchase_id", sa.BigInteger(), sa.ForeignKey("purchases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount_xtr", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "ledger",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("award_id", sa.BigInteger(), sa.ForeignKey("bonus_awards.id", ondelete="SET NULL")),
        sa.Column("payload", json_type),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("currency IN ('coins_cash','coins_bonus')", name="ck_ledger_currency"),
    )
    op.create_index("ix_ledger_user_id", "ledger", ["user_id"])

    op.create_table(
        "feature_flags",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("flag", sa.String(length=64), nullable=False),
        sa.Column("variant", sa.String(length=32), nullable=False, server_default="on"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "flag", name="uq_feature_flags_user_flag"),
    )

    turnover_table = sa.table(
        "turnover_rules",
        sa.column("game", sa.String()),
        sa.column("contribution", sa.SmallInteger()),
    )
    op.bulk_insert(
        turnover_table,
        [
            {"game": "slot", "contribution": 100},
            {"game": "crash", "contribution": 50},
            {"game": "duel", "contribution": 25},
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM turnover_rules")
    op.drop_table("feature_flags")
    op.drop_table("ledger")
    op.drop_table("refunds")
    op.drop_table("purchases")
    op.drop_table("turnover_rules")
    op.drop_table("bonus_awards")
    op.drop_table("wallets")
    op.drop_table("users")
