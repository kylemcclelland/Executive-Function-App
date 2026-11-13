# ruff: noqa: E501
"""Devotion discovery metadata: one nullable JSON column for themes, tradition, durations and provenance.

Purely additive and backward compatible: existing devotions simply have NULL. Not applied to any
database by this change. Down: drops the column.
"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("devotions", sa.Column("discovery", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("devotions", "discovery")
