"""Devotions: editorially approved prayer content, its editorial log, and reader bookmarks.

Purely additive: four new tables; no existing table or row is changed, and no devotion or prayer
text is inserted. The catalogue starts empty and stays unpublished until a named editor enters
sourced content and a named approver approves it.
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def quoted(*values: str) -> str:
    return ",".join(f"'{value}'" for value in values)


# Frozen here on purpose: a migration must keep meaning what it meant when it was written.
TEXT_STATUSES = quoted("proposed", "source_verified", "pending_approval", "approved")
STATUSES = quoted("proposed", "source_verified", "pending_approval", "approved", "published")
LICENSES = quoted("unverified", "public_domain", "licensed", "permission_granted")


def upgrade():
    op.create_table(
        "devotions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("subtitle", sa.String(300), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("estimated_minutes", sa.Integer(), nullable=True),
        sa.Column("overview", sa.Text(), nullable=False),
        sa.Column("background", sa.Text(), nullable=True),
        sa.Column("significance", sa.Text(), nullable=True),
        sa.Column("references", sa.JSON(), nullable=False),
        sa.Column("instructions", sa.JSON(), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("source_verified_by", sa.String(255), nullable=True),
        sa.Column("source_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.String(255), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_hash", sa.String(64), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("slug", name="uq_devotions_slug"),
        sa.CheckConstraint(f"status IN ({STATUSES})", name="devotion_status"),
        sa.CheckConstraint(
            "estimated_minutes IS NULL OR estimated_minutes > 0", name="devotion_estimate",
        ),
        sa.CheckConstraint(
            "status NOT IN ('approved','published') OR (approved_by IS NOT NULL "
            "AND approved_at IS NOT NULL AND approved_hash IS NOT NULL)",
            name="devotion_approval_recorded",
        ),
        sa.CheckConstraint(
            "status <> 'published' OR published_at IS NOT NULL", name="devotion_published_at",
        ),
    )
    op.create_table(
        "prayer_texts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "devotion_id", sa.Uuid(), sa.ForeignKey("devotions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slot", sa.String(60), nullable=False),
        sa.Column("language", sa.String(12), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(300), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_translation", sa.Boolean(), nullable=False),
        sa.Column("translator", sa.String(300), nullable=True),
        sa.Column("source_title", sa.String(500), nullable=True),
        sa.Column("source_edition", sa.String(300), nullable=True),
        sa.Column("source_url", sa.String(2000), nullable=True),
        sa.Column("attribution", sa.String(1000), nullable=True),
        sa.Column("license_status", sa.String(20), nullable=False),
        sa.Column("license_notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("entered_by", sa.String(255), nullable=False),
        sa.Column("source_verified_by", sa.String(255), nullable=True),
        sa.Column("source_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.String(255), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_hash", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("devotion_id", "slot", "language", name="uq_prayer_text_version"),
        sa.CheckConstraint(f"status IN ({TEXT_STATUSES})", name="prayer_text_status"),
        sa.CheckConstraint(f"license_status IN ({LICENSES})", name="prayer_text_license"),
        sa.CheckConstraint("length(trim(body)) > 0", name="prayer_text_body"),
        sa.CheckConstraint(
            "status = 'proposed' OR (source_title IS NOT NULL AND attribution IS NOT NULL "
            "AND license_status <> 'unverified' AND source_verified_by IS NOT NULL "
            "AND source_verified_at IS NOT NULL)", name="prayer_text_source_recorded",
        ),
        sa.CheckConstraint(
            "status <> 'approved' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL "
            "AND approved_hash IS NOT NULL)", name="prayer_text_approval_recorded",
        ),
    )
    op.create_index("ix_prayer_texts_devotion_id", "prayer_texts", ["devotion_id"])
    op.create_table(
        "devotion_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "devotion_id", sa.Uuid(), sa.ForeignKey("devotions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "text_id", sa.Uuid(), sa.ForeignKey("prayer_texts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("from_status", sa.String(20), nullable=True),
        sa.Column("to_status", sa.String(20), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_devotion_events_devotion", "devotion_events", ["devotion_id", "created_at"],
    )
    op.create_table(
        "devotion_bookmarks",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column(
            "devotion_id", sa.Uuid(), sa.ForeignKey("devotions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


def downgrade():
    op.drop_table("devotion_bookmarks")
    op.drop_table("devotion_events")
    op.drop_table("prayer_texts")
    op.drop_table("devotions")
