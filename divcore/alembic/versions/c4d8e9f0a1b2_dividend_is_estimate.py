"""add div_cal_trade.dividend_is_estimate

Revision ID: c4d8e9f0a1b2
Revises: b3c7d8e9f0a1
Create Date: 2026-09-26

Flags a dividend_amount that was auto-filled from an estimate (buy $ ÷ pre-ex
close × per-share amount) rather than typed by the user, so the Trades tab can
render it in a distinct "estimate" colour. Defaults false; the flag is cleared
the moment the user edits the dividend cell.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c4d8e9f0a1b2"
down_revision: Union[str, Sequence[str], None] = "b3c7d8e9f0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "div_cal_trade",
        sa.Column(
            "dividend_is_estimate",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("div_cal_trade", "dividend_is_estimate")
