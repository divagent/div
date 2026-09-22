"""rename div_cal_trade.predicted_ex_date -> ex_date

Revision ID: c8d2e3f4a5b6
Revises: b7c1d2e3f4a5
Create Date: 2026-09-08

Renames the column and its index. The unique constraint keeps its name
(uq_div_cal_trade_symbol_ex_date) since it already reads "ex_date"; Postgres
tracks it by the underlying column, which the rename updates automatically.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "b7c1d2e3f4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("div_cal_trade", "predicted_ex_date", new_column_name="ex_date")
    op.execute(
        "ALTER INDEX ix_div_cal_trade_predicted_ex_date "
        "RENAME TO ix_div_cal_trade_ex_date"
    )


def downgrade() -> None:
    op.execute(
        "ALTER INDEX ix_div_cal_trade_ex_date "
        "RENAME TO ix_div_cal_trade_predicted_ex_date"
    )
    op.alter_column("div_cal_trade", "ex_date", new_column_name="predicted_ex_date")
