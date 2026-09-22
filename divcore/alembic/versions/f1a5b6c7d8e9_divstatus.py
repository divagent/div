"""rename div_cal_trade.predicted_amount -> amount and add divstatus

Revision ID: f1a5b6c7d8e9
Revises: e0f4a5b6c7d8
Create Date: 2026-09-09

A tick is one concept: it has one `amount`, and a `divstatus` (Confirmed |
Prediction) that says how firm that amount is — so the `predicted_` prefix is
dropped. `divstatus` is nullable; existing rows read back as NULL until the
predict/publish flow re-stamps them.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f1a5b6c7d8e9"
down_revision: Union[str, Sequence[str], None] = "e0f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("div_cal_trade", "predicted_amount", new_column_name="amount")
    op.add_column(
        "div_cal_trade", sa.Column("divstatus", sa.String(length=20), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("div_cal_trade", "divstatus")
    op.alter_column("div_cal_trade", "amount", new_column_name="predicted_amount")
