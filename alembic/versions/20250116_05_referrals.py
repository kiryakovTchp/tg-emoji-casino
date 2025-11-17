"""referrals and user tracking

Revision ID: 20250116_05
Revises: 20250116_04
Create Date: 2025-11-16 19:55:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20250116_05"
down_revision = "20250116_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("ref_code", sa.String(length=16), unique=True))
    op.add_column("users", sa.Column("paid_spins_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("paid_crash_bets_count", sa.Integer(), nullable=False, server_default="0"))
    op.create_table(
        "referrals",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ref_code", sa.String(length=32), nullable=False, index=True),
        sa.Column("inviter_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invitee_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("activated", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("invitee_id", name="uq_referrals_invitee"),
    )


def downgrade() -> None:
    op.drop_table("referrals")
    op.drop_column("users", "paid_crash_bets_count")
    op.drop_column("users", "paid_spins_count")
    op.drop_column("users", "ref_code")
