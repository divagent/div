"""change div_cal_trade.quantity to integer (whole shares)

Revision ID: e0f4a5b6c7d8
Revises: d9e3f4a5b6c7
Create Date: 2026-09-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e0f4a5b6c7d8"
down_revision: Union[str, Sequence[str], None] = "d9e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "div_cal_trade",
        "quantity",
        type_=sa.Integer(),
        postgresql_using="round(quantity)::integer",
    )


def downgrade() -> None:
    op.alter_column(
        "div_cal_trade",
        "quantity",
        type_=sa.Numeric(precision=14, scale=4),
        postgresql_using="quantity::numeric(14,4)",
    )
