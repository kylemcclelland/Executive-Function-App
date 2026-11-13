# ruff: noqa: E501
"""The user's default calendar for Today: one nullable preference column.

Additive and trivial on both dialects (a plain ADD COLUMN, no table rebuild, no constraint):
``users.calendar_provider`` holds 'traditional' or 'current' (validated at the API); NULL keeps
the application default. No existing row or other column is touched. Down: drops the column.
"""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("calendar_provider", sa.String(20), nullable=True))


def downgrade():
    op.drop_column("users", "calendar_provider")
