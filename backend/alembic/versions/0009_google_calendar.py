"""Google Calendar connections and pending OAuth states.

Purely additive: two new tables; no existing table or row is changed.
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "google_calendar_connections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("google_account_identifier", sa.String(255), nullable=True),
        sa.Column("google_account_email", sa.String(320), nullable=True),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=True),
        sa.Column("granted_scopes", sa.Text(), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_successful_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("connection_status", sa.String(20), nullable=False),
        sa.CheckConstraint(
            "connection_status IN ('active','needs_reauth','disconnected')", name="gcal_status",
        ),
    )
    op.create_index(
        "ix_google_calendar_connections_user_id", "google_calendar_connections", ["user_id"],
    )
    op.create_index(
        "uq_gcal_one_live_connection_per_user", "google_calendar_connections", ["user_id"],
        unique=True,
        sqlite_where=sa.text("connection_status <> 'disconnected'"),
        postgresql_where=sa.text("connection_status <> 'disconnected'"),
    )
    op.create_table(
        "google_oauth_states",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("state_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("encrypted_code_verifier", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_google_oauth_states_user_id", "google_oauth_states", ["user_id"])
    op.create_index("ix_google_oauth_states_expires", "google_oauth_states", ["expires_at"])


def downgrade():
    op.drop_table("google_oauth_states")
    op.drop_table("google_calendar_connections")
