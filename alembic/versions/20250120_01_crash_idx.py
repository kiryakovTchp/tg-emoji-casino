"""Ensure single active crash round"""

from __future__ import annotations

from typing import Union, Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20250120_01_crash_idx'
down_revision: Union[str, None] = '20250117_01_crash_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_crash_rounds_active",
        "crash_rounds",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status IN ('betting','flying')"),
        sqlite_where=sa.text("status IN ('betting','flying')"),
    )


def downgrade() -> None:
    op.drop_index("uq_crash_rounds_active", table_name="crash_rounds")
