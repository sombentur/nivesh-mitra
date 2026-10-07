"""index_daily.open may be empty (Groww omits it for BSE stocks and recent sessions)

Revision ID: a8d3e6f1c2b4
Revises: f7c1a2b3d4e5
Create Date: 2026-09-30 21:50:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a8d3e6f1c2b4"
down_revision: Union[str, None] = "f7c1a2b3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column("index_daily", "open", existing_type=sa.Float(), nullable=True)
        return
    # SQLite can't relax NOT NULL in place; rebuild the table explicitly to keep it WITHOUT ROWID.
    op.execute(
        "CREATE TABLE index_daily_new (symbol VARCHAR(40) NOT NULL, date DATE NOT NULL, open FLOAT, high FLOAT NOT NULL, "
        "low FLOAT NOT NULL, close FLOAT NOT NULL, PRIMARY KEY (symbol, date)) WITHOUT ROWID"
    )
    op.execute("INSERT INTO index_daily_new SELECT symbol, date, open, high, low, close FROM index_daily")
    op.execute("DROP TABLE index_daily")
    op.execute("ALTER TABLE index_daily_new RENAME TO index_daily")


def downgrade() -> None:
    op.execute("DELETE FROM index_daily WHERE open IS NULL")
    op.execute(
        "CREATE TABLE index_daily_old (symbol VARCHAR(40) NOT NULL, date DATE NOT NULL, open FLOAT NOT NULL, high FLOAT NOT NULL, "
        "low FLOAT NOT NULL, close FLOAT NOT NULL, PRIMARY KEY (symbol, date)) WITHOUT ROWID"
    )
    op.execute("INSERT INTO index_daily_old SELECT symbol, date, open, high, low, close FROM index_daily")
    op.execute("DROP TABLE index_daily")
    op.execute("ALTER TABLE index_daily_old RENAME TO index_daily")
