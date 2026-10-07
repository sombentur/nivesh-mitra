"""news_briefs: the tone of each news pulse, scored against the Nifty's move

Revision ID: f7c1a2b3d4e5
Revises: e5b2c8d4a1f9
Create Date: 2026-09-30 21:30:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f7c1a2b3d4e5"
down_revision: Union[str, None] = "e5b2c8d4a1f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "news_briefs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("overall", sa.String(length=10), nullable=False),
        sa.Column("positive", sa.Integer(), nullable=False),
        sa.Column("negative", sa.Integer(), nullable=False),
        sa.Column("neutral", sa.Integer(), nullable=False),
        sa.Column("headlines", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_news_briefs_session_date", "news_briefs", ["session_date"])


def downgrade() -> None:
    op.drop_index("ix_news_briefs_session_date", table_name="news_briefs")
    op.drop_table("news_briefs")
