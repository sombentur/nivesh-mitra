"""instruments.history_complete: a stock's full price history has been downloaded

Revision ID: e5b2c8d4a1f9
Revises: c3a9d1e4b7f2
Create Date: 2026-09-30 19:30:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5b2c8d4a1f9"
down_revision: Union[str, None] = "c3a9d1e4b7f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A plain ADD COLUMN: batch mode would rebuild the table, which price_daily's foreign key makes fragile.
    op.execute("DROP TABLE IF EXISTS _alembic_tmp_instruments")  # left over by an earlier failed attempt
    op.add_column("instruments", sa.Column("history_complete", sa.Boolean(), nullable=False, server_default=sa.false()))
    # Stocks whose history reaches back beyond the ranking scan's ~100-day window were fully downloaded already.
    op.execute("UPDATE instruments SET history_complete = 1 WHERE history_start IS NOT NULL AND history_start < date('now', '-150 days')")


def downgrade() -> None:
    with op.batch_alter_table("instruments") as batch:
        batch.drop_column("history_complete")
