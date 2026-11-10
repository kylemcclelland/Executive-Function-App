# ruff: noqa: E501
"""Saved Divine Office prayers: a user's own saved psalms, canticles, hymns and antiphons.

Purely additive: one new table (saved_office_units); no existing table or row is changed. Each row is a server-verified snapshot of one
prayer from the Divine Office with its provenance, private to the user who saved it (removed with the user). Down: drops that table.
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "saved_office_units",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("unit_key", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("title_latin", sa.String(300), nullable=False),
        sa.Column("title_english", sa.String(300), nullable=True),
        sa.Column("date_specific", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source_hour", sa.String(20), nullable=False),
        sa.Column("source_date", sa.Date(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("source", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "unit_key", name="uq_saved_office_user_unit"),
    )
    op.create_index("ix_saved_office_user", "saved_office_units", ["user_id", "created_at"])


def downgrade():
    op.drop_index("ix_saved_office_user", table_name="saved_office_units")
    op.drop_table("saved_office_units")
