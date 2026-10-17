"""merge heads and add itr_returns

Revision ID: c4f1a9b2d3e5
Revises: 3cc18d9706a2, 9f2c4a7b1e3d
Create Date: 2026-10-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c4f1a9b2d3e5"
down_revision: Union[str, Sequence[str], None] = ("3cc18d9706a2", "9f2c4a7b1e3d")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "itr_returns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column("fy_label", sa.String(length=10), nullable=False),
        sa.Column("ay_label", sa.String(length=10), nullable=False),
        sa.Column("form_type", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("input_json", sa.Text(), nullable=True),
        sa.Column("draft_json", sa.Text(), nullable=True),
        sa.Column("output_json", sa.Text(), nullable=True),
        sa.Column("schema_version", sa.String(length=50), nullable=True),
        sa.Column("generated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("member_id", "ay_label", name="uq_itr_return_member_ay"),
    )
    op.create_index(op.f("ix_itr_returns_id"), "itr_returns", ["id"], unique=False)
    op.create_index(
        op.f("ix_itr_returns_member_id"), "itr_returns", ["member_id"], unique=False
    )
    op.create_index(
        op.f("ix_itr_returns_ay_label"), "itr_returns", ["ay_label"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_itr_returns_ay_label"), table_name="itr_returns")
    op.drop_index(op.f("ix_itr_returns_member_id"), table_name="itr_returns")
    op.drop_index(op.f("ix_itr_returns_id"), table_name="itr_returns")
    op.drop_table("itr_returns")
