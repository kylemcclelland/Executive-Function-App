from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base, UTCDateTime, utcnow


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class User(Timestamps, Base):
    __tablename__ = "users"
    __table_args__ = (Index("uq_users_clerk_user_id", "clerk_user_id", unique=True),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    # The verified Clerk user id (`sub`). NULL for the pre-authentication legacy user until its
    # owner claims it, so no new account can ever reach that data by signing up.
    clerk_user_id: Mapped[str | None] = mapped_column(String(255))
    timezone: Mapped[str] = mapped_column(String(100), default="UTC")


class Task(Timestamps, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("status IN ('todo','in_progress','completed')", name="task_status"),
        CheckConstraint("estimated_minutes IS NULL OR estimated_minutes > 0", name="task_estimate"),
        Index("ix_tasks_user_scheduled", "user_id", "scheduled_date"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True,
    )
    milestone_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("project_milestones.id", ondelete="SET NULL"),
    )
    project_position: Mapped[int | None]
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="todo")
    due_date: Mapped[date | None]
    scheduled_date: Mapped[date | None]
    estimated_minutes: Mapped[int | None]
    next_action: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    steps: Mapped[list["Step"]] = relationship(
        back_populates="task", cascade="all, delete-orphan",
        order_by="(Step.position, Step.id)", lazy="selectin",
    )
    project: Mapped["Project | None"] = relationship(lazy="selectin", viewonly=True)

    @property
    def project_name(self) -> str | None:
        return self.project.name if self.project else None


class Step(Base):
    __tablename__ = "task_steps"
    __table_args__ = (CheckConstraint("position >= 0", name="step_position"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    position: Mapped[int]
    is_completed: Mapped[bool] = mapped_column(default=False)
    task: Mapped[Task] = relationship(back_populates="steps")


class InboxItem(Timestamps, Base):
    __tablename__ = "inbox_items"
    __table_args__ = (
        CheckConstraint("status IN ('unprocessed','processed','archived')", name="inbox_status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="unprocessed")
    was_converted: Mapped[bool] = mapped_column(default=False)
    converted_task_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), unique=True,
    )
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class Project(Timestamps, Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','paused','someday','completed')", name="project_status",
        ),
        Index("ix_projects_user_status", "user_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="active")
    target_date: Mapped[date | None]
    next_action: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class Milestone(Timestamps, Base):
    __tablename__ = "project_milestones"
    __table_args__ = (Index("ix_milestones_project", "project_id", "position"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    target_date: Mapped[date | None]
    position: Mapped[int] = mapped_column(default=0)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class ProjectNote(Timestamps, Base):
    __tablename__ = "project_notes"
    __table_args__ = (Index("ix_project_notes_project", "project_id", "updated_at"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    title: Mapped[str | None] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text)


class ProjectUpdate(Base):
    """A manually entered progress update or work-session log entry."""

    __tablename__ = "project_updates"
    __table_args__ = (
        CheckConstraint("kind IN ('progress','session')", name="project_update_kind"),
        Index("ix_project_updates_project", "project_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(20), default="session")
    summary: Mapped[str] = mapped_column(Text)
    next_step: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class WorkSession(Timestamps, Base):
    """A focused block of work on a project, optionally on one of its tasks.

    ``ended_at``/``elapsed_seconds`` stay empty for an interrupted session: the true end is unknown.
    """

    __tablename__ = "work_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','finished','interrupted')", name="work_session_status",
        ),
        CheckConstraint(
            "planned_minutes IS NULL OR planned_minutes > 0", name="work_session_planned",
        ),
        Index(
            "uq_work_sessions_one_active", "user_id", unique=True,
            sqlite_where=text("status = 'active'"), postgresql_where=text("status = 'active'"),
        ),
        Index("ix_work_sessions_project", "project_id", "started_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    task_id: Mapped[UUID | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))
    intention: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active")
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    planned_minutes: Mapped[int | None]
    elapsed_seconds: Mapped[int | None]
    accomplished: Mapped[str | None] = mapped_column(Text)
    resume_note: Mapped[str | None] = mapped_column(Text)
    project: Mapped[Project] = relationship(lazy="selectin", viewonly=True)
    task: Mapped[Task | None] = relationship(lazy="selectin", viewonly=True)

    @property
    def project_name(self) -> str:
        return self.project.name

    @property
    def task_title(self) -> str | None:
        return self.task.title if self.task else None


NOTE_TYPES = ("general", "reading_note", "quotation", "reflection", "research", "question")
LINK_TYPES = ("related_to", "supports", "contradicts", "develops", "responds_to")


def _in_list(values: tuple[str, ...]) -> str:
    return ",".join(f"'{value}'" for value in values)


class Book(Timestamps, Base):
    """A book worth keeping. Deliberately has no reading status, progress, rating or shelf."""

    __tablename__ = "books"
    __table_args__ = (
        Index("ix_books_user_title", "user_id", "title"),
        # Lets a future Goodreads import match existing books without duplicating them.
        Index(
            "uq_books_user_goodreads", "user_id", "goodreads_id", unique=True,
            sqlite_where=text("goodreads_id IS NOT NULL"),
            postgresql_where=text("goodreads_id IS NOT NULL"),
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    authors: Mapped[list[str]] = mapped_column(JSON, default=list)
    isbn_10: Mapped[str | None] = mapped_column(String(10))
    isbn_13: Mapped[str | None] = mapped_column(String(13))
    publication_year: Mapped[int | None]
    publisher: Mapped[str | None] = mapped_column(String(200))
    edition: Mapped[str | None] = mapped_column(String(200))
    cover_url: Mapped[str | None] = mapped_column(String(2000))
    goodreads_id: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text)


class NoteTag(Base):
    __tablename__ = "note_tags"
    __table_args__ = (Index("ix_note_tags_tag", "tag"),)
    note_id: Mapped[UUID] = mapped_column(
        ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True,
    )
    tag: Mapped[str] = mapped_column(String(50), primary_key=True)


class Note(Timestamps, Base):
    """A commonplace-book entry. Independent of any book or project; links are optional."""

    __tablename__ = "notes"
    __table_args__ = (
        CheckConstraint(f"note_type IN ({_in_list(NOTE_TYPES)})", name="note_type"),
        Index("ix_notes_user_updated", "user_id", "updated_at"),
        Index("ix_notes_book", "book_id"),
        Index("ix_notes_project", "project_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text, default="")
    note_type: Mapped[str] = mapped_column(String(20), default="general")
    # Deleting a book or project never deletes a note; the link is simply cleared.
    book_id: Mapped[UUID | None] = mapped_column(ForeignKey("books.id", ondelete="SET NULL"))
    project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"),
    )
    source_location: Mapped[str | None] = mapped_column(String(300))
    # Remembers where a note came from when its book was deleted, so attribution survives.
    former_book: Mapped[str | None] = mapped_column(String(500))
    tag_rows: Mapped[list[NoteTag]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="NoteTag.tag",
    )
    book: Mapped[Book | None] = relationship(lazy="selectin", viewonly=True)
    project: Mapped[Project | None] = relationship(lazy="selectin", viewonly=True)

    @property
    def tags(self) -> list[str]:
        return sorted((row.tag for row in self.tag_rows), key=lambda tag: (tag.casefold(), tag))

    @property
    def book_title(self) -> str | None:
        return self.book.title if self.book else None

    @property
    def project_name(self) -> str | None:
        return self.project.name if self.project else None

    @property
    def excerpt(self) -> str:
        return (self.content or "")[:240]


class NoteLink(Base):
    """A manual, user-authored connection between two notes (an edge for a future idea graph).

    Directional types read source -> target. Symmetric types are stored once, with the two
    note ids in a canonical order, so "A related to B" and "B related to A" cannot coexist.
    """

    __tablename__ = "note_links"
    __table_args__ = (
        CheckConstraint("source_note_id <> target_note_id", name="note_link_not_self"),
        CheckConstraint(f"link_type IN ({_in_list(LINK_TYPES)})", name="note_link_type"),
        UniqueConstraint("source_note_id", "target_note_id", "link_type", name="uq_note_link"),
        Index("ix_note_links_source", "source_note_id"),
        Index("ix_note_links_target", "target_note_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    source_note_id: Mapped[UUID] = mapped_column(ForeignKey("notes.id", ondelete="CASCADE"))
    target_note_id: Mapped[UUID] = mapped_column(ForeignKey("notes.id", ondelete="CASCADE"))
    link_type: Mapped[str] = mapped_column(String(20))
    explanation: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


CONNECTION_STATUSES = ("active", "needs_reauth", "disconnected")


class GoogleCalendarConnection(Base):
    """A user's authorization to read one Google Calendar account. Holds no access token.

    The refresh token is stored only encrypted. Version 1 allows one live connection per user (the
    partial unique index); supporting several accounts later means replacing that index with
    ``UNIQUE (user_id, google_account_identifier)``. ``disconnected`` rows keep no token.
    """

    __tablename__ = "google_calendar_connections"
    __table_args__ = (
        CheckConstraint(
            f"connection_status IN ({_in_list(CONNECTION_STATUSES)})", name="gcal_status",
        ),
        Index(
            "uq_gcal_one_live_connection_per_user", "user_id", unique=True,
            sqlite_where=text("connection_status <> 'disconnected'"),
            postgresql_where=text("connection_status <> 'disconnected'"),
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    google_account_identifier: Mapped[str | None] = mapped_column(String(255))
    google_account_email: Mapped[str | None] = mapped_column(String(320))
    encrypted_refresh_token: Mapped[str | None] = mapped_column(Text)
    granted_scopes: Mapped[str] = mapped_column(Text, default="")
    connected_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)
    last_successful_sync_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    connection_status: Mapped[str] = mapped_column(String(20), default="active")


class GoogleOAuthState(Base):
    """One pending authorization attempt: expiring, single use, bound to the initiating user.

    Only a hash of the state value is stored; the PKCE verifier is stored encrypted.
    """

    __tablename__ = "google_oauth_states"
    __table_args__ = (Index("ix_google_oauth_states_expires", "expires_at"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    state_hash: Mapped[str] = mapped_column(String(64), unique=True)
    encrypted_code_verifier: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    consumed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class CoverLookup(Base):
    """Remembers what Open Library said about an ISBN, so it is never asked twice needlessly.

    Only definite answers are stored (a cover exists, or none does). Errors and rate limits are
    transient and are never cached. The answer is a fact about the ISBN, not about a user.
    """

    __tablename__ = "cover_lookups"
    __table_args__ = (
        CheckConstraint("result IN ('found','not_found')", name="cover_lookup_result"),
    )
    isbn: Mapped[str] = mapped_column(String(13), primary_key=True)
    result: Mapped[str] = mapped_column(String(12))
    cover_id: Mapped[int | None] = mapped_column(BigInteger())
    looked_up_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class CoverServiceState(Base):
    """Cooldown after Open Library asks us to slow down; persists across restarts."""

    __tablename__ = "cover_service_state"
    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    blocked_until: Mapped[datetime | None] = mapped_column(UTCDateTime())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class DailyPriority(Base):
    __tablename__ = "daily_priorities"
    __table_args__ = (
        UniqueConstraint("user_id", "priority_date", "position", name="uq_priority_position"),
        UniqueConstraint("user_id", "priority_date", "task_id", name="uq_priority_task"),
        CheckConstraint("position >= 0 AND position < 3", name="priority_limit"),
        Index("ix_priorities_user_date", "user_id", "priority_date"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    priority_date: Mapped[date]
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    position: Mapped[int]
