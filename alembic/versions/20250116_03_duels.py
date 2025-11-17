"""duels table

Revision ID: 20250116_03
Revises: 20250116_02
Create Date: 2025-11-16 19:35:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20250116_03"
down_revision = "20250116_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

    op.create_table(
        "duels",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger()),
        sa.Column("thread_id", sa.BigInteger()),
        sa.Column("starter_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("opponent_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("winner_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("stake_amount", sa.BigInteger(), nullable=False),
        sa.Column("stake_currency", sa.String(length=16), nullable=False),
        sa.Column("bank_cash", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("bank_bonus", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("wins_starter", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("wins_opponent", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("rounds", json_type, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("pair_key", sa.String(length=64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_duels_pair_key", "duels", ["pair_key"])
    op.create_index("ix_duels_chat", "duels", ["chat_id"])


def downgrade() -> None:
    op.drop_index("ix_duels_chat", table_name="duels")
    op.drop_index("ix_duels_pair_key", table_name="duels")
    op.drop_table("duels")
