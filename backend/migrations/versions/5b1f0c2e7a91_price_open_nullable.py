"""price_daily.open may be empty (Groww omits recent daily opens)

Revision ID: 5b1f0c2e7a91
Revises: 9edb80f12e6e
Create Date: 2026-09-30 17:20:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "5b1f0c2e7a91"
down_revision: Union[str, None] = "9edb80f12e6e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column("price_daily", "open", existing_type=sa.Float(), nullable=True)
        return
    # SQLite can't relax NOT NULL in place; rebuild the table explicitly to keep it WITHOUT ROWID.
    op.execute(
        "CREATE TABLE price_daily_new (instrument_id INTEGER NOT NULL, date DATE NOT NULL, open FLOAT, high FLOAT NOT NULL, "
        "low FLOAT NOT NULL, close FLOAT NOT NULL, volume BIGINT NOT NULL, PRIMARY KEY (instrument_id, date), "
        "FOREIGN KEY(instrument_id) REFERENCES instruments (id)) WITHOUT ROWID"
    )
    op.execute("INSERT INTO price_daily_new SELECT instrument_id, date, open, high, low, close, volume FROM price_daily")
    op.execute("DROP TABLE price_daily")
    op.execute("ALTER TABLE price_daily_new RENAME TO price_daily")


def downgrade() -> None:
    op.execute("DELETE FROM price_daily WHERE open IS NULL")
