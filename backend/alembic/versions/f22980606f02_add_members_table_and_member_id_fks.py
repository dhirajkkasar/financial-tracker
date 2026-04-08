"""add members table and member_id FKs

Revision ID: f22980606f02
Revises: e47b3dc61761
Create Date: 2026-04-08 18:29:56.365774

"""
import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f22980606f02'
down_revision: Union[str, None] = 'e47b3dc61761'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create members table
    op.create_table(
        'members',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pan', sa.String(length=10), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('pan'),
    )
    op.create_index(op.f('ix_members_id'), 'members', ['id'], unique=False)

    # 2. Add member_id columns (nullable initially for backfill)
    op.add_column('assets', sa.Column('member_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_assets_member_id'), 'assets', ['member_id'], unique=False)
    op.create_foreign_key(None, 'assets', 'members', ['member_id'], ['id'])

    op.add_column('important_data', sa.Column('member_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_important_data_member_id'), 'important_data', ['member_id'], unique=False)
    op.create_foreign_key(None, 'important_data', 'members', ['member_id'], ['id'])

    op.add_column('portfolio_snapshots', sa.Column('member_id', sa.Integer(), nullable=True))
    op.drop_index(op.f('ix_portfolio_snapshots_date'), table_name='portfolio_snapshots')
    op.create_index(op.f('ix_portfolio_snapshots_date'), 'portfolio_snapshots', ['date'], unique=False)
    op.create_index(op.f('ix_portfolio_snapshots_member_id'), 'portfolio_snapshots', ['member_id'], unique=False)
    op.create_unique_constraint('uq_snapshot_member_date', 'portfolio_snapshots', ['member_id', 'date'])
    op.create_foreign_key(None, 'portfolio_snapshots', 'members', ['member_id'], ['id'])

    # 3. Seed default member from env vars and backfill existing rows
    pan = os.environ.get("DEFAULT_MEMBER_PAN")
    name = os.environ.get("DEFAULT_MEMBER_NAME")
    if not pan or not name:
        raise RuntimeError(
            "Set DEFAULT_MEMBER_PAN and DEFAULT_MEMBER_NAME env vars before running this migration. "
            "Example: DEFAULT_MEMBER_PAN=ABCDE1234F DEFAULT_MEMBER_NAME='Dhiraj' uv run alembic upgrade head"
        )

    conn = op.get_bind()
    conn.execute(
        sa.text("INSERT INTO members (pan, name, is_default) VALUES (:pan, :name, 1)"),
        {"pan": pan.upper(), "name": name},
    )
    result = conn.execute(sa.text("SELECT id FROM members WHERE pan = :pan"), {"pan": pan.upper()})
    default_id = result.scalar_one()

    conn.execute(sa.text("UPDATE assets SET member_id = :mid"), {"mid": default_id})
    conn.execute(sa.text("UPDATE important_data SET member_id = :mid"), {"mid": default_id})
    conn.execute(sa.text("UPDATE portfolio_snapshots SET member_id = :mid"), {"mid": default_id})


def downgrade() -> None:
    op.drop_constraint(None, 'portfolio_snapshots', type_='foreignkey')
    op.drop_constraint('uq_snapshot_member_date', 'portfolio_snapshots', type_='unique')
    op.drop_index(op.f('ix_portfolio_snapshots_member_id'), table_name='portfolio_snapshots')
    op.drop_index(op.f('ix_portfolio_snapshots_date'), table_name='portfolio_snapshots')
    op.create_index(op.f('ix_portfolio_snapshots_date'), 'portfolio_snapshots', ['date'], unique=1)
    op.drop_column('portfolio_snapshots', 'member_id')
    op.drop_constraint(None, 'important_data', type_='foreignkey')
    op.drop_index(op.f('ix_important_data_member_id'), table_name='important_data')
    op.drop_column('important_data', 'member_id')
    op.drop_constraint(None, 'assets', type_='foreignkey')
    op.drop_index(op.f('ix_assets_member_id'), table_name='assets')
    op.drop_column('assets', 'member_id')
    op.drop_index(op.f('ix_members_id'), table_name='members')
    op.drop_table('members')
