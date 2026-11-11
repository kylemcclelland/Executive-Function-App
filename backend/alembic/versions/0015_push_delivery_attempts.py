# ruff: noqa: E501
"""Push delivery attempts: the dispatcher's durable work queue, one row per occurrence and browser.

Purely additive: one new table and one nullable column on push_subscriptions (``revoked_at``,
set when the push service reports the subscription gone). Not applied to any database by this
change. Down: drops both.
"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("push_subscriptions", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "push_delivery_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entry_id", sa.Uuid(), sa.ForeignKey("rule_of_life_entries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subscription_id", sa.Uuid(), sa.ForeignKey("push_subscriptions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("occurrence_date", sa.Date(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("claimed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("entry_id", "occurrence_date", "subscription_id", name="uq_push_attempt"),
    )
    op.create_index("ix_push_attempts_status_due", "push_delivery_attempts", ["status", "due_at"])
    op.create_index("ix_push_attempts_user", "push_delivery_attempts", ["user_id"])


def downgrade():
    op.drop_index("ix_push_attempts_user", table_name="push_delivery_attempts")
    op.drop_index("ix_push_attempts_status_due", table_name="push_delivery_attempts")
    op.drop_table("push_delivery_attempts")
    op.drop_column("push_subscriptions", "revoked_at")
