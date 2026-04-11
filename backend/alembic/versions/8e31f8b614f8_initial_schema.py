"""initial_schema

Revision ID: 8e31f8b614f8
Revises:
Create Date: 2026-04-10 19:52:14.173547

Consolidated single-revision schema. Replaces the full prior migration chain.
For existing DBs: already stamped at this revision via `alembic stamp head`.
For fresh DBs: `alembic upgrade head` runs this alone and creates everything.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8e31f8b614f8'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # members must be created first — assets/important_data/portfolio_snapshots FK to it
    op.create_table(
        'members',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('pan', sa.String(length=10), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('pan'),
    )
    op.create_index(op.f('ix_members_id'), 'members', ['id'], unique=False)

    op.create_table(
        'assets',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('identifier', sa.String(length=100), nullable=True),
        sa.Column('asset_type', sa.Enum(
            'STOCK_IN', 'STOCK_US', 'MF', 'FD', 'RD', 'PPF', 'EPF', 'NPS',
            'GOLD', 'SGB', 'REAL_ESTATE', 'RSU', name='assettype'
        ), nullable=False),
        sa.Column('asset_class', sa.Enum(
            'EQUITY', 'DEBT', 'GOLD', 'REAL_ESTATE', 'MIXED', name='assetclass'
        ), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('mfapi_scheme_code', sa.String(length=20), nullable=True),
        sa.Column('scheme_category', sa.String(length=100), nullable=True),
        sa.Column('member_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['member_id'], ['members.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_assets_id'), 'assets', ['id'], unique=False)
    op.create_index(op.f('ix_assets_member_id'), 'assets', ['member_id'], unique=False)

    op.create_table(
        'goals',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('target_amount_inr', sa.Integer(), nullable=False),
        sa.Column('target_date', sa.Date(), nullable=False),
        sa.Column('assumed_return_pct', sa.Float(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_goals_id'), 'goals', ['id'], unique=False)

    op.create_table(
        'important_data',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('category', sa.Enum(
            'BANK', 'MF_FOLIO', 'IDENTITY', 'INSURANCE', 'ACCOUNT', 'OTHER',
            name='importantdatacategory'
        ), nullable=False),
        sa.Column('label', sa.String(length=255), nullable=False),
        sa.Column('fields_json', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('member_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['member_id'], ['members.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_important_data_category'), 'important_data', ['category'], unique=False)
    op.create_index(op.f('ix_important_data_id'), 'important_data', ['id'], unique=False)
    op.create_index(op.f('ix_important_data_member_id'), 'important_data', ['member_id'], unique=False)

    op.create_table(
        'interest_rates',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('instrument', sa.Enum('PPF', 'EPF', name='instrumenttype'), nullable=False),
        sa.Column('rate_pct', sa.Float(), nullable=False),
        sa.Column('effective_from', sa.Date(), nullable=False),
        sa.Column('effective_to', sa.Date(), nullable=True),
        sa.Column('fy_label', sa.String(length=10), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('instrument', 'effective_from', name='uq_instrument_effective_from'),
    )
    op.create_index(op.f('ix_interest_rates_id'), 'interest_rates', ['id'], unique=False)
    op.create_index(op.f('ix_interest_rates_instrument'), 'interest_rates', ['instrument'], unique=False)

    op.create_table(
        'portfolio_snapshots',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('total_value_paise', sa.Integer(), nullable=False),
        sa.Column('breakdown_json', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('member_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['member_id'], ['members.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('member_id', 'date', name='uq_snapshot_member_date'),
    )
    op.create_index('ix_portfolio_snapshots_date', 'portfolio_snapshots', ['date'], unique=False)
    op.create_index('ix_portfolio_snapshots_id', 'portfolio_snapshots', ['id'], unique=False)
    op.create_index(op.f('ix_portfolio_snapshots_member_id'), 'portfolio_snapshots', ['member_id'], unique=False)

    op.create_table(
        'fd_details',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('bank', sa.String(length=100), nullable=False),
        sa.Column('fd_type', sa.Enum('FD', 'RD', name='fdtype'), nullable=False),
        sa.Column('principal_amount', sa.Integer(), nullable=False),
        sa.Column('interest_rate_pct', sa.Float(), nullable=False),
        sa.Column('compounding', sa.Enum(
            'MONTHLY', 'QUARTERLY', 'HALF_YEARLY', 'YEARLY', 'SIMPLE', name='compoundingtype'
        ), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('maturity_date', sa.Date(), nullable=False),
        sa.Column('maturity_amount', sa.Integer(), nullable=True),
        sa.Column('is_matured', sa.Boolean(), nullable=False),
        sa.Column('tds_applicable', sa.Boolean(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_fd_details_asset_id'), 'fd_details', ['asset_id'], unique=True)
    op.create_index(op.f('ix_fd_details_id'), 'fd_details', ['id'], unique=False)

    op.create_table(
        'goal_allocations',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('goal_id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('allocation_pct', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id']),
        sa.ForeignKeyConstraint(['goal_id'], ['goals.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('goal_id', 'asset_id', name='uq_goal_asset'),
    )
    op.create_index(op.f('ix_goal_allocations_asset_id'), 'goal_allocations', ['asset_id'], unique=False)
    op.create_index(op.f('ix_goal_allocations_goal_id'), 'goal_allocations', ['goal_id'], unique=False)
    op.create_index(op.f('ix_goal_allocations_id'), 'goal_allocations', ['id'], unique=False)

    op.create_table(
        'price_cache',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('price_inr', sa.Integer(), nullable=False),
        sa.Column('fetched_at', sa.DateTime(), nullable=False),
        sa.Column('source', sa.String(length=100), nullable=True),
        sa.Column('is_stale', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_price_cache_asset_id'), 'price_cache', ['asset_id'], unique=True)
    op.create_index(op.f('ix_price_cache_id'), 'price_cache', ['id'], unique=False)

    op.create_table(
        'transactions',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('txn_id', sa.String(length=64), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.Enum(
            'BUY', 'SELL', 'SIP', 'REDEMPTION', 'DIVIDEND', 'INTEREST',
            'CONTRIBUTION', 'WITHDRAWAL', 'SWITCH_IN', 'SWITCH_OUT', 'BONUS',
            'SPLIT', 'VEST', 'TRANSFER', 'BILLING', name='transactiontype'
        ), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('units', sa.Float(), nullable=True),
        sa.Column('price_per_unit', sa.Float(), nullable=True),
        sa.Column('forex_rate', sa.Float(), nullable=True),
        sa.Column('amount_inr', sa.Integer(), nullable=False),
        sa.Column('charges_inr', sa.Integer(), nullable=False),
        sa.Column('lot_id', sa.String(length=36), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_transactions_asset_id'), 'transactions', ['asset_id'], unique=False)
    op.create_index('ix_transactions_asset_id_date', 'transactions', ['asset_id', 'date'], unique=False)
    op.create_index(op.f('ix_transactions_date'), 'transactions', ['date'], unique=False)
    op.create_index(op.f('ix_transactions_id'), 'transactions', ['id'], unique=False)
    op.create_index(op.f('ix_transactions_lot_id'), 'transactions', ['lot_id'], unique=False)
    op.create_index(op.f('ix_transactions_txn_id'), 'transactions', ['txn_id'], unique=True)

    op.create_table(
        'valuations',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('value_inr', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_valuations_asset_id'), 'valuations', ['asset_id'], unique=False)
    op.create_index(op.f('ix_valuations_id'), 'valuations', ['id'], unique=False)

    op.create_table(
        'cas_snapshots',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('closing_units', sa.Float(), nullable=False),
        sa.Column('nav_price_inr', sa.Integer(), nullable=False),
        sa.Column('market_value_inr', sa.Integer(), nullable=False),
        sa.Column('total_cost_inr', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_cas_snapshots_asset_id'), 'cas_snapshots', ['asset_id'], unique=False)
    op.create_index(op.f('ix_cas_snapshots_id'), 'cas_snapshots', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_cas_snapshots_id'), table_name='cas_snapshots')
    op.drop_index(op.f('ix_cas_snapshots_asset_id'), table_name='cas_snapshots')
    op.drop_table('cas_snapshots')
    op.drop_index(op.f('ix_valuations_id'), table_name='valuations')
    op.drop_index(op.f('ix_valuations_asset_id'), table_name='valuations')
    op.drop_table('valuations')
    op.drop_index(op.f('ix_transactions_txn_id'), table_name='transactions')
    op.drop_index(op.f('ix_transactions_lot_id'), table_name='transactions')
    op.drop_index(op.f('ix_transactions_id'), table_name='transactions')
    op.drop_index(op.f('ix_transactions_date'), table_name='transactions')
    op.drop_index('ix_transactions_asset_id_date', table_name='transactions')
    op.drop_index(op.f('ix_transactions_asset_id'), table_name='transactions')
    op.drop_table('transactions')
    op.drop_index(op.f('ix_price_cache_id'), table_name='price_cache')
    op.drop_index(op.f('ix_price_cache_asset_id'), table_name='price_cache')
    op.drop_table('price_cache')
    op.drop_index(op.f('ix_goal_allocations_id'), table_name='goal_allocations')
    op.drop_index(op.f('ix_goal_allocations_goal_id'), table_name='goal_allocations')
    op.drop_index(op.f('ix_goal_allocations_asset_id'), table_name='goal_allocations')
    op.drop_table('goal_allocations')
    op.drop_index(op.f('ix_fd_details_id'), table_name='fd_details')
    op.drop_index(op.f('ix_fd_details_asset_id'), table_name='fd_details')
    op.drop_table('fd_details')
    op.drop_index(op.f('ix_portfolio_snapshots_member_id'), table_name='portfolio_snapshots')
    op.drop_index('ix_portfolio_snapshots_id', table_name='portfolio_snapshots')
    op.drop_index('ix_portfolio_snapshots_date', table_name='portfolio_snapshots')
    op.drop_table('portfolio_snapshots')
    op.drop_index(op.f('ix_interest_rates_instrument'), table_name='interest_rates')
    op.drop_index(op.f('ix_interest_rates_id'), table_name='interest_rates')
    op.drop_table('interest_rates')
    op.drop_index(op.f('ix_important_data_member_id'), table_name='important_data')
    op.drop_index(op.f('ix_important_data_id'), table_name='important_data')
    op.drop_index(op.f('ix_important_data_category'), table_name='important_data')
    op.drop_table('important_data')
    op.drop_index(op.f('ix_goals_id'), table_name='goals')
    op.drop_table('goals')
    op.drop_index(op.f('ix_assets_member_id'), table_name='assets')
    op.drop_index(op.f('ix_assets_id'), table_name='assets')
    op.drop_table('assets')
    op.drop_index(op.f('ix_members_id'), table_name='members')
    op.drop_table('members')

    # Drop PostgreSQL ENUM types (no-op on SQLite)
    op.execute("DROP TYPE IF EXISTS transactiontype")
    op.execute("DROP TYPE IF EXISTS instrumenttype")
    op.execute("DROP TYPE IF EXISTS compoundingtype")
    op.execute("DROP TYPE IF EXISTS fdtype")
    op.execute("DROP TYPE IF EXISTS importantdatacategory")
    op.execute("DROP TYPE IF EXISTS assetclass")
    op.execute("DROP TYPE IF EXISTS assettype")
