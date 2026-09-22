"""rename divstatus value 'Confirmed' -> 'Declared'

Revision ID: b3c7d8e9f0a1
Revises: a2b6c7d8e9f0
Create Date: 2026-09-14

A dividend the board has announced is *declared*, not "confirmed" — so the
firmness value is renamed. `divstatus` is a free-form String(20) (no enum/check
constraint), so this is a pure data update. Google Calendar events that still
carry the old "Confirmed" value are normalized on read (see gcal_api._parse_event)
and self-heal on the next predict/reconcile upsert.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3c7d8e9f0a1"
down_revision: Union[str, Sequence[str], None] = "a2b6c7d8e9f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE div_cal_trade SET divstatus = 'Declared' WHERE divstatus = 'Confirmed'")


def downgrade() -> None:
    op.execute("UPDATE div_cal_trade SET divstatus = 'Confirmed' WHERE divstatus = 'Declared'")
