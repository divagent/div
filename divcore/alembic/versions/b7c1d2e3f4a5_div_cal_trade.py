"""rename dividend_predictions -> div_cal_trade and add trade-log columns

Revision ID: b7c1d2e3f4a5
Revises: 0d602e83a78e
Create Date: 2026-09-08

Renames the table (and its constraint + indexes) and adds the user-entered trade
fields (total dollars) plus a hidden flag for the Trades tab. Existing prediction
rows are preserved; new columns are null (hidden defaults to false).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b7c1d2e3f4a5"
down_revision: Union[str, Sequence[str], None] = "0d602e83a78e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table("dividend_predictions", "div_cal_trade")
    op.execute(
        "ALTER TABLE div_cal_trade "
        "RENAME CONSTRAINT uq_prediction_symbol_ex_date "
        "TO uq_div_cal_trade_symbol_ex_date"
    )
    for old, new in (
        ("ix_dividend_predictions_google_event_id", "ix_div_cal_trade_google_event_id"),
        ("ix_dividend_predictions_id", "ix_div_cal_trade_id"),
        ("ix_dividend_predictions_predicted_ex_date", "ix_div_cal_trade_predicted_ex_date"),
        ("ix_dividend_predictions_symbol", "ix_div_cal_trade_symbol"),
    ):
        op.execute(f"ALTER INDEX {old} RENAME TO {new}")

    op.add_column("div_cal_trade", sa.Column("company_name", sa.String(length=255), nullable=True))
    op.add_column("div_cal_trade", sa.Column("payment_date", sa.Date(), nullable=True))
    op.add_column("div_cal_trade", sa.Column("purchase_date", sa.Date(), nullable=True))
    op.add_column("div_cal_trade", sa.Column("purchase_amount", sa.Numeric(precision=14, scale=2), nullable=True))
    op.add_column("div_cal_trade", sa.Column("sell_date", sa.Date(), nullable=True))
    op.add_column("div_cal_trade", sa.Column("sell_amount", sa.Numeric(precision=14, scale=2), nullable=True))
    op.add_column("div_cal_trade", sa.Column("dividend_amount", sa.Numeric(precision=14, scale=2), nullable=True))
    op.add_column(
        "div_cal_trade",
        sa.Column("hidden", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    for col in (
        "hidden",
        "dividend_amount",
        "sell_amount",
        "sell_date",
        "purchase_amount",
        "purchase_date",
        "payment_date",
        "company_name",
    ):
        op.drop_column("div_cal_trade", col)

    for new, old in (
        ("ix_div_cal_trade_google_event_id", "ix_dividend_predictions_google_event_id"),
        ("ix_div_cal_trade_id", "ix_dividend_predictions_id"),
        ("ix_div_cal_trade_predicted_ex_date", "ix_dividend_predictions_predicted_ex_date"),
        ("ix_div_cal_trade_symbol", "ix_dividend_predictions_symbol"),
    ):
        op.execute(f"ALTER INDEX {new} RENAME TO {old}")
    op.execute(
        "ALTER TABLE div_cal_trade "
        "RENAME CONSTRAINT uq_div_cal_trade_symbol_ex_date "
        "TO uq_prediction_symbol_ex_date"
    )
    op.rename_table("div_cal_trade", "dividend_predictions")
