"""add_transfer_transaction_type

Revision ID: a1b2c3d4e5f6
Revises: 2788f59d52d0
Create Date: 2026-03-20 18:00:00.000000

Note: SQLite stores enums as VARCHAR, so no column type change is needed.
For PostgreSQL, the enum type must be altered to include 'TRANSFER'.
This migration is a no-op for SQLite but handles PostgreSQL via try/except.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '2788f59d52d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite: enums stored as VARCHAR — no migration needed.
    # PostgreSQL: add 'TRANSFER' to the transactiontype enum.
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute("ALTER TYPE transactiontype ADD VALUE IF NOT EXISTS 'TRANSFER'")


def downgrade() -> None:
    # PostgreSQL enums cannot easily remove values; this is intentionally a no-op.
    # For SQLite, nothing was changed.
    pass
