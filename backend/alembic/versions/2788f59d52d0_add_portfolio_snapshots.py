"""add_portfolio_snapshots

Revision ID: 2788f59d52d0
Revises: 0453f3ff0410
Create Date: 2026-03-20 16:47:09.279564

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2788f59d52d0'
down_revision: Union[str, None] = '0453f3ff0410'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'portfolio_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('total_value_paise', sa.Integer(), nullable=False),
        sa.Column('breakdown_json', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_portfolio_snapshots_date', 'portfolio_snapshots', ['date'], unique=True)
    op.create_index('ix_portfolio_snapshots_id', 'portfolio_snapshots', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_portfolio_snapshots_date', table_name='portfolio_snapshots')
    op.drop_index('ix_portfolio_snapshots_id', table_name='portfolio_snapshots')
    op.drop_table('portfolio_snapshots')
