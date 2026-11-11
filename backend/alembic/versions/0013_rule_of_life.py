# ruff: noqa: E501
"""Rule of Life: a user's scheduled prayers and their completed/skipped occurrences.

Purely additive: two new tables; no existing table or row is changed. Not applied to any database by this change. Down: drops both tables.
"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rule_of_life_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("ref", sa.String(120), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("local_time", sa.Time(), nullable=False),
        sa.Column("timezone", sa.String(100), nullable=False),
        sa.Column("recurrence", sa.String(10), nullable=False),
        sa.Column("weekdays", sa.JSON(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("notify", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("fingerprint", sa.String(300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "fingerprint", name="uq_rule_entry_fingerprint"),
    )
    op.create_index("ix_rule_entry_user", "rule_of_life_entries", ["user_id", "local_time"])
    op.create_table(
        "rule_of_life_occurrences",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("entry_id", sa.Uuid(), sa.ForeignKey("rule_of_life_entries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("occurrence_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("marked_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("entry_id", "occurrence_date", name="uq_rule_occurrence"),
    )


def downgrade():
    op.drop_table("rule_of_life_occurrences")
    op.drop_index("ix_rule_entry_user", table_name="rule_of_life_entries")
    op.drop_table("rule_of_life_entries")
