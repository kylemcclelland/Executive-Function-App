"""Remember the verified numeric Open Library cover ID alongside each cached lookup.

Purely additive: one nullable column; no existing row is changed.
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("cover_lookups", sa.Column("cover_id", sa.BigInteger(), nullable=True))


def downgrade():
    op.drop_column("cover_lookups", "cover_id")
