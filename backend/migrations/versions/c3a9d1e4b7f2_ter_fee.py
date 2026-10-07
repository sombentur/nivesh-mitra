"""mf_scheme_facts.fee: the fund house's own fee inside the total expense ratio

Revision ID: c3a9d1e4b7f2
Revises: 5b1f0c2e7a91
Create Date: 2026-09-30 18:10:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3a9d1e4b7f2"
down_revision: Union[str, None] = "5b1f0c2e7a91"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("mf_scheme_facts") as batch:
        batch.add_column(sa.Column("fee", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("mf_scheme_facts") as batch:
        batch.drop_column("fee")
