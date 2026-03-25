"""add_billing_transaction_type

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-25 12:00:00.000000

Note: SQLite stores enums as VARCHAR, so no column type change is needed.
For PostgreSQL, the enum type must be altered to include 'BILLING'.
This migration is a no-op for SQLite but handles PostgreSQL via try/except.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite: enums stored as VARCHAR — no migration needed.
    # PostgreSQL: add 'BILLING' to the transactiontype enum.
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute("ALTER TYPE transactiontype ADD VALUE IF NOT EXISTS 'BILLING'")


def downgrade() -> None:
    # PostgreSQL enums cannot easily remove values; this is intentionally a no-op.
    # For SQLite, nothing was changed.
    pass
