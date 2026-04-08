"""merge_heads

Revision ID: e47b3dc61761
Revises: 5bcf15222da5, b2c3d4e5f6a7
Create Date: 2026-04-08 18:29:51.808994

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e47b3dc61761'
down_revision: Union[str, None] = ('5bcf15222da5', 'b2c3d4e5f6a7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
