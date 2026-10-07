"""Download every stock's daily history again from Groww's candle-data feed (current, split-adjusted, real opens)

Revision ID: b9e4f7a2c3d5
Revises: a8d3e6f1c2b4
Create Date: 2026-10-03 13:30:00
"""

from typing import Sequence, Union

from alembic import op

revision: str = "b9e4f7a2c3d5"
down_revision: Union[str, None] = "a8d3e6f1c2b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The history stored so far came from the backtesting feed (not adjusted, empty opens, double-counted volume).
    # Clearing the flag makes the "stock price history" job replace it, stock by stock, at the next start.
    op.execute("UPDATE instruments SET history_complete = 0")


def downgrade() -> None:
    pass
