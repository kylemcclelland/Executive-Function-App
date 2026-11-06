"""Add the library: books, notes, tags, and manual note-to-note connections.

Purely additive: no existing table or row is changed. Notes keep their book/project
association with ON DELETE SET NULL, so deleting either never deletes a note.
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

NOTE_TYPES = "'general','reading_note','quotation','reflection','research','question'"
LINK_TYPES = "'related_to','supports','contradicts','develops','responds_to'"


def timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade():
    op.create_table(
        "books",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("authors", sa.JSON(), nullable=False),
        sa.Column("isbn_10", sa.String(10), nullable=True),
        sa.Column("isbn_13", sa.String(13), nullable=True),
        sa.Column("publication_year", sa.Integer(), nullable=True),
        sa.Column("publisher", sa.String(200), nullable=True),
        sa.Column("edition", sa.String(200), nullable=True),
        sa.Column("cover_url", sa.String(2000), nullable=True),
        sa.Column("goodreads_id", sa.String(50), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        *timestamps(),
    )
    op.create_index("ix_books_user_id", "books", ["user_id"])
    op.create_index("ix_books_user_title", "books", ["user_id", "title"])
    op.create_index(
        "uq_books_user_goodreads", "books", ["user_id", "goodreads_id"], unique=True,
        sqlite_where=sa.text("goodreads_id IS NOT NULL"),
        postgresql_where=sa.text("goodreads_id IS NOT NULL"),
    )
    op.create_table(
        "notes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("note_type", sa.String(20), nullable=False),
        sa.Column("book_id", sa.Uuid(), sa.ForeignKey("books.id", ondelete="SET NULL")),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="SET NULL")),
        sa.Column("source_location", sa.String(300), nullable=True),
        sa.Column("former_book", sa.String(500), nullable=True),
        *timestamps(),
        sa.CheckConstraint(f"note_type IN ({NOTE_TYPES})", name="note_type"),
    )
    op.create_index("ix_notes_user_id", "notes", ["user_id"])
    op.create_index("ix_notes_user_updated", "notes", ["user_id", "updated_at"])
    op.create_index("ix_notes_book", "notes", ["book_id"])
    op.create_index("ix_notes_project", "notes", ["project_id"])
    op.create_table(
        "note_tags",
        sa.Column(
            "note_id", sa.Uuid(), sa.ForeignKey("notes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("tag", sa.String(50), primary_key=True),
    )
    op.create_index("ix_note_tags_tag", "note_tags", ["tag"])
    op.create_table(
        "note_links",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "source_note_id", sa.Uuid(), sa.ForeignKey("notes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_note_id", sa.Uuid(), sa.ForeignKey("notes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("link_type", sa.String(20), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("source_note_id <> target_note_id", name="note_link_not_self"),
        sa.CheckConstraint(f"link_type IN ({LINK_TYPES})", name="note_link_type"),
        sa.UniqueConstraint("source_note_id", "target_note_id", "link_type", name="uq_note_link"),
    )
    op.create_index("ix_note_links_user_id", "note_links", ["user_id"])
    op.create_index("ix_note_links_source", "note_links", ["source_note_id"])
    op.create_index("ix_note_links_target", "note_links", ["target_note_id"])


def downgrade():
    for table in ("note_links", "note_tags", "notes", "books"):
        op.drop_table(table)
