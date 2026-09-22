"""initial: nasdaq and nyse tables

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "nasdaq",
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("security_name", sa.String(), nullable=True),
        sa.Column("market_category", sa.String(), nullable=True),
        sa.Column("test_issue", sa.Boolean(), nullable=False),
        sa.Column("financial_status", sa.String(), nullable=True),
        sa.Column("round_lot_size", sa.Integer(), nullable=True),
        sa.Column("etf", sa.Boolean(), nullable=False),
        sa.Column("next_shares", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("symbol"),
    )
    op.create_table(
        "nyse",
        sa.Column("act_symbol", sa.String(), nullable=False),
        sa.Column("security_name", sa.String(), nullable=True),
        sa.Column("exchange", sa.String(), nullable=True),
        sa.Column("cqs_symbol", sa.String(), nullable=True),
        sa.Column("etf", sa.Boolean(), nullable=False),
        sa.Column("round_lot_size", sa.Integer(), nullable=True),
        sa.Column("test_issue", sa.Boolean(), nullable=False),
        sa.Column("nasdaq_symbol", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("act_symbol"),
    )


def downgrade() -> None:
    op.drop_table("nyse")
    op.drop_table("nasdaq")
