"""edgar market-cap enrich columns

Revision ID: 0003_edgar_marketcap
Revises: 0002_edgar
Create Date: 2026-08-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_edgar_marketcap"
down_revision: Union[str, None] = "0002_edgar"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("edgar", sa.Column("shares_outstanding", sa.BigInteger(), nullable=True))
    op.add_column("edgar", sa.Column("shares_as_of", sa.Date(), nullable=True))
    op.add_column("edgar", sa.Column("close_price", sa.Numeric(20, 4), nullable=True))
    op.add_column("edgar", sa.Column("close_date", sa.Date(), nullable=True))
    op.add_column("edgar", sa.Column("market_cap", sa.BigInteger(), nullable=True))
    op.add_column("edgar", sa.Column("enriched_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("edgar", "enriched_at")
    op.drop_column("edgar", "market_cap")
    op.drop_column("edgar", "close_date")
    op.drop_column("edgar", "close_price")
    op.drop_column("edgar", "shares_as_of")
    op.drop_column("edgar", "shares_outstanding")
