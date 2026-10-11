"""add member tax profiles and loss carryforwards

Revision ID: 9f2c4a7b1e3d
Revises: a0fa4c347bea
Create Date: 2026-10-11 10:00:00.000000

"""
from typing import Sequence, Union

import enum
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9f2c4a7b1e3d'
down_revision: Union[str, None] = 'a0fa4c347bea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'member_tax_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('member_id', sa.Integer(), nullable=False),
        sa.Column('fy_label', sa.String(length=10), nullable=False),
        sa.Column('total_income_inr', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['member_id'], ['members.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('member_id', 'fy_label', name='uq_member_tax_profile'),
    )
    op.create_index(op.f('ix_member_tax_profiles_id'), 'member_tax_profiles', ['id'], unique=False)
    op.create_index(op.f('ix_member_tax_profiles_member_id'), 'member_tax_profiles', ['member_id'], unique=False)

    loss_type_enum = sa.Enum('STCL', 'LTCL', name='losstype', create_type=True)
    op.create_table(
        'tax_loss_carryforwards',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('member_id', sa.Integer(), nullable=False),
        sa.Column('fy_label', sa.String(length=10), nullable=False),
        sa.Column('loss_type', loss_type_enum, nullable=False),
        sa.Column('amount_inr', sa.Float(), nullable=False),
        sa.Column('remaining_inr', sa.Float(), nullable=False),
        sa.Column('expires_fy_label', sa.String(length=10), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['member_id'], ['members.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('member_id', 'fy_label', 'loss_type', name='uq_carryforward'),
    )
    op.create_index(op.f('ix_tax_loss_carryforwards_id'), 'tax_loss_carryforwards', ['id'], unique=False)
    op.create_index(op.f('ix_tax_loss_carryforwards_member_id'), 'tax_loss_carryforwards', ['member_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_tax_loss_carryforwards_member_id'), table_name='tax_loss_carryforwards')
    op.drop_index(op.f('ix_tax_loss_carryforwards_id'), table_name='tax_loss_carryforwards')
    op.drop_table('tax_loss_carryforwards')
    op.drop_index(op.f('ix_member_tax_profiles_member_id'), table_name='member_tax_profiles')
    op.drop_index(op.f('ix_member_tax_profiles_id'), table_name='member_tax_profiles')
    op.drop_table('member_tax_profiles')
