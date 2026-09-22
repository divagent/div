"""rename div_cal_trade.symbol -> ticker

Revision ID: a2b6c7d8e9f0
Revises: f1a5b6c7d8e9
Create Date: 2026-09-09

The canonical stock-ticker field is `ticker` end-to-end (wire schemas, the Google
Calendar private property, and this column). Only the column is renamed; the
existing unique constraint / index names (uq_div_cal_trade_symbol_ex_date,
ix_div_cal_trade_symbol) are left as-is — they keep working over the renamed
column, and renaming them buys nothing.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a2b6c7d8e9f0"
down_revision: Union[str, Sequence[str], None] = "f1a5b6c7d8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("div_cal_trade", "symbol", new_column_name="ticker")


def downgrade() -> None:
    op.alter_column("div_cal_trade", "ticker", new_column_name="symbol")
