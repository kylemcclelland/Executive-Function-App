# ruff: noqa: E501
"""Resumable cover enrichment: one job row per user so the worker can continue on its own.

Purely additive: one new table (cover_enrichment_jobs); no existing table or row is changed. Not
applied to any database by this change. Down: drops the table.
"""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cover_enrichment_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="running"),
        sa.Column("books_checked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("covers_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("without_cover", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unavailable_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(120), nullable=True),
        sa.Column("skip_ids", sa.JSON(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_progress_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_cover_job_user"),
        sa.CheckConstraint("status IN ('running','paused','done')", name="cover_job_status"),
    )
    op.create_index("ix_cover_jobs_due", "cover_enrichment_jobs", ["status", "next_run_at"])


def downgrade():
    op.drop_index("ix_cover_jobs_due", table_name="cover_enrichment_jobs")
    op.drop_table("cover_enrichment_jobs")
