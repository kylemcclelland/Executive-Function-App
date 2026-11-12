from datetime import date, datetime, time
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
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


class CoverEnrichmentJob(Base):
    """A user's resumable cover-enrichment job: the worker continues it until nothing is left.

    One row per user. ``next_run_at`` is when the worker may touch it again (a cooldown, a backoff,
    or right now); ``claimed_until`` is a bounded lease so two worker passes can never run the same
    job at once. ``skip_ids`` carries forward the book ids each batch finished with, exactly as the
    interactive endpoint does. Counters only ever grow; completed work survives any failure.
    """

    __tablename__ = "cover_enrichment_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('running','paused','done')", name="cover_job_status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(String(10), default="running")
    books_checked: Mapped[int] = mapped_column(Integer, default=0)
    covers_found: Mapped[int] = mapped_column(Integer, default=0)
    without_cover: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    unavailable_streak: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(120))
    skip_ids: Mapped[list] = mapped_column(JSON, default=list)
    next_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    claimed_until: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_progress_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
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


# --- Devotions: editorially approved prayer content -------------------------------------------
# Shared catalogue (not user-owned). Nothing here is ever generated by the application: every
# prayer text is entered by a named human editor from a cited source and approved by a named
# approver. See docs/devotions-architecture.md.

DEVOTION_STATUSES = ("proposed", "source_verified", "pending_approval", "approved", "published")
PRAYER_TEXT_STATUSES = DEVOTION_STATUSES[:4]  # a text is approved; only a devotion is published
# "restricted": the owner's terms do not clearly permit republishing, so the wording is withheld and
# only the citation and link are kept. "unverified": nobody has checked yet.
# Neither can be verified.
LICENSE_STATUSES = ("unverified", "restricted", "public_domain", "licensed", "permission_granted")


class Devotion(Timestamps, Base):
    """The page around a prayer: overview, instructions, structure and citations. No prayer text.

    ``steps`` refer to prayer texts by ``slot`` and never contain prayer wording, so the exact
    wording is approved separately (see ``PrayerText``). ``approved_hash`` fingerprints the content
    that was approved; if the content changes the approval no longer applies.
    """

    __tablename__ = "devotions"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_devotions_slug"),
        CheckConstraint(f"status IN ({_in_list(DEVOTION_STATUSES)})", name="devotion_status"),
        CheckConstraint(
            "estimated_minutes IS NULL OR estimated_minutes > 0", name="devotion_estimate",
        ),
        # The database itself refuses an approved or published row that carries no approval record.
        CheckConstraint(
            "status NOT IN ('approved','published') OR (approved_by IS NOT NULL "
            "AND approved_at IS NOT NULL AND approved_hash IS NOT NULL)",
            name="devotion_approval_recorded",
        ),
        CheckConstraint(
            "status <> 'published' OR published_at IS NOT NULL", name="devotion_published_at",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(300))
    subtitle: Mapped[str | None] = mapped_column(String(300))
    category: Mapped[str | None] = mapped_column(String(100))
    estimated_minutes: Mapped[int | None]
    overview: Mapped[str] = mapped_column(Text)
    background: Mapped[str | None] = mapped_column(Text)
    significance: Mapped[str | None] = mapped_column(Text)
    references: Mapped[list[dict]] = mapped_column(JSON, default=list)
    instructions: Mapped[list[str]] = mapped_column(JSON, default=list)
    steps: Mapped[list[dict]] = mapped_column(JSON, default=list)
    # Names the choice when steps are grouped (for the Rosary: "Mysteries"); NULL when they are not.
    choice_label: Mapped[str | None] = mapped_column(String(60))
    # Where the explanatory prose came from, e.g. "ai_draft": shown as unapproved until approved.
    prose_origin: Mapped[str | None] = mapped_column(String(40))
    # Research/discovery metadata for imported prayers (themes, tradition, focus, durations,
    # provenance). Free-form JSON so the editorial schema stays untouched; NULL for older rows.
    discovery: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    created_by: Mapped[str] = mapped_column(String(255))
    source_verified_by: Mapped[str | None] = mapped_column(String(255))
    source_verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    approved_by: Mapped[str | None] = mapped_column(String(255))
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    approved_hash: Mapped[str | None] = mapped_column(String(64))
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    texts: Mapped[list["PrayerText"]] = relationship(
        back_populates="devotion", cascade="all, delete-orphan", lazy="selectin",
        order_by="(PrayerText.position, PrayerText.slot, PrayerText.language)",
    )


class PrayerText(Timestamps, Base):
    """The exact wording of one prayer in one language, with where it came from.

    One row per (devotion, slot, language): the Latin and the English of the same prayer share a
    ``slot`` and are approved separately. The wording is stored exactly as entered.
    """

    __tablename__ = "prayer_texts"
    __table_args__ = (
        UniqueConstraint("devotion_id", "slot", "language", name="uq_prayer_text_version"),
        CheckConstraint(f"status IN ({_in_list(PRAYER_TEXT_STATUSES)})", name="prayer_text_status"),
        CheckConstraint(
            f"license_status IN ({_in_list(LICENSE_STATUSES)})", name="prayer_text_license",
        ),
        # Wording may be absent only while a text is a proposal (citation kept, wording withheld).
        CheckConstraint("status = 'proposed' OR length(trim(body)) > 0", name="prayer_text_body"),
        # Nothing moves past "proposed" without a cited source, attribution and cleared rights.
        CheckConstraint(
            "status = 'proposed' OR (source_title IS NOT NULL AND attribution IS NOT NULL "
            "AND license_status NOT IN ('unverified','restricted') "
            "AND source_verified_by IS NOT NULL AND source_verified_at IS NOT NULL)",
            name="prayer_text_source_recorded",
        ),
        CheckConstraint(
            "status <> 'approved' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL "
            "AND approved_hash IS NOT NULL)", name="prayer_text_approval_recorded",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    devotion_id: Mapped[UUID] = mapped_column(
        ForeignKey("devotions.id", ondelete="CASCADE"), index=True,
    )
    slot: Mapped[str] = mapped_column(String(60))
    language: Mapped[str] = mapped_column(String(12))
    position: Mapped[int] = mapped_column(default=0)
    title: Mapped[str | None] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    is_translation: Mapped[bool] = mapped_column(default=False)
    translator: Mapped[str | None] = mapped_column(String(300))
    source_title: Mapped[str | None] = mapped_column(String(500))
    # The issuing authority or author, the edition, and its publication date, exactly as known.
    source_authority: Mapped[str | None] = mapped_column(String(500))
    source_edition: Mapped[str | None] = mapped_column(String(300))
    source_date: Mapped[str | None] = mapped_column(String(100))
    source_url: Mapped[str | None] = mapped_column(String(2000))
    # When the wording was copied from the source (evidence for a reviewer).
    source_retrieved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    attribution: Mapped[str | None] = mapped_column(String(1000))
    license_status: Mapped[str] = mapped_column(String(20), default="unverified")
    license_notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    entered_by: Mapped[str] = mapped_column(String(255))
    source_verified_by: Mapped[str | None] = mapped_column(String(255))
    source_verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    approved_by: Mapped[str | None] = mapped_column(String(255))
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    approved_hash: Mapped[str | None] = mapped_column(String(64))
    devotion: Mapped[Devotion] = relationship(back_populates="texts")


class DevotionEvent(Base):
    """Append-only editorial log: who created, changed, moved or removed what, and when."""

    __tablename__ = "devotion_events"
    __table_args__ = (Index("ix_devotion_events_devotion", "devotion_id", "created_at"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    devotion_id: Mapped[UUID] = mapped_column(ForeignKey("devotions.id", ondelete="CASCADE"))
    text_id: Mapped[UUID | None] = mapped_column(ForeignKey("prayer_texts.id", ondelete="SET NULL"))
    actor: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(40))
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str | None] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class DevotionBookmark(Base):
    """A reader's own favourite. Deliberately only that: no dates, counts, streaks or history."""

    __tablename__ = "devotion_bookmarks"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    devotion_id: Mapped[UUID] = mapped_column(
        ForeignKey("devotions.id", ondelete="CASCADE"), primary_key=True,
    )


class SavedOfficeUnit(Base):
    """A prayer one user saved from the Divine Office: a server-verified snapshot with provenance.

    The server copies the text from the Divinum Officium engine when saving (never from the client),
    so it reopens unchanged whatever upstream later does. ``unit_key`` identifies the selection: a
    content hash for fixed prayers (psalms, canticles, hymns), plus the date and hour for an
    antiphon, which belongs to its day.
    """

    __tablename__ = "saved_office_units"
    __table_args__ = (
        UniqueConstraint("user_id", "unit_key", name="uq_saved_office_user_unit"),
        Index("ix_saved_office_user", "user_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    unit_key: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20))
    title_latin: Mapped[str] = mapped_column(String(300))
    title_english: Mapped[str | None] = mapped_column(String(300))
    date_specific: Mapped[bool] = mapped_column(default=False)
    source_hour: Mapped[str] = mapped_column(String(20))
    source_date: Mapped[date] = mapped_column()
    content: Mapped[dict] = mapped_column(JSON)
    source: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class RuleOfLifeEntry(Timestamps, Base):
    """One prayer in a user's Rule of Life: a stable reference to a prayer plus its recurrence.

    No prayer text is stored. ``kind``/``ref`` name the prayer: a saved Divine Office prayer
    (its id), a whole Office hour (its slug, resolved for each occurrence's own date) or a
    library devotion such as the Rosary (its slug). ``fingerprint`` makes an accidental
    duplicate impossible while distinct times stay allowed.
    """

    __tablename__ = "rule_of_life_entries"
    __table_args__ = (
        UniqueConstraint("user_id", "fingerprint", name="uq_rule_entry_fingerprint"),
        Index("ix_rule_entry_user", "user_id", "local_time"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(20))
    ref: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(300))
    local_time: Mapped[time] = mapped_column()
    timezone: Mapped[str] = mapped_column(String(100))
    recurrence: Mapped[str] = mapped_column(String(10))
    weekdays: Mapped[list] = mapped_column(JSON, default=list)
    start_date: Mapped[date] = mapped_column()
    notify: Mapped[bool] = mapped_column(default=False)
    active: Mapped[bool] = mapped_column(default=True)
    fingerprint: Mapped[str] = mapped_column(String(300))


class PushSubscription(Timestamps, Base):
    """One browser's Web Push subscription, owned by one user. Holds no VAPID private key.

    The endpoint URL and encryption keys are exactly what the browser's PushManager issued; we
    store nothing else about the device. ``endpoint_hash`` (SHA-256 of the endpoint) carries the
    uniqueness constraint, since endpoints can exceed index limits. An endpoint identifies one
    browser profile globally, so re-registering it (even from another signed-in account) moves it
    rather than duplicating it. ``failure_count``/``last_failure_at`` let the Phase 2 sender
    retire dead subscriptions; nothing reads them yet.
    """

    __tablename__ = "push_subscriptions"
    __table_args__ = (
        UniqueConstraint("endpoint_hash", name="uq_push_subscription_endpoint"),
        Index("ix_push_subscriptions_user", "user_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    endpoint: Mapped[str] = mapped_column(String(2000))
    endpoint_hash: Mapped[str] = mapped_column(String(64))
    # Browser-generated ECDH public key and auth secret (base64url), used only to encrypt pushes.
    p256dh: Mapped[str] = mapped_column(String(512))
    auth: Mapped[str] = mapped_column(String(512))
    failure_count: Mapped[int] = mapped_column(default=0)
    last_failure_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # Set when the push service said the subscription is gone (404/410); the row is kept for the
    # audit trail but is never sent to again. The browser can simply re-subscribe.
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


ATTEMPT_STATUSES = ("pending", "delivered", "failed", "expired")


class PushDeliveryAttempt(Timestamps, Base):
    """One reminder owed to one browser for one prayer occurrence; the dispatcher's work queue.

    The unique constraint makes a duplicate dispatch *claim* impossible; `claimed_until` is a
    bounded lease so two overlapping dispatcher runs never own the same attempt and a crashed
    run's claims expire on their own. After a temporary failure the same column is the backoff
    timer. "delivered" means the push service accepted the message — not that the device showed
    it; Web Push is at-least-once under retries, deduplicated on the device by the notification
    tag. No payload, endpoint or secret is stored: only the outcome.
    """

    __tablename__ = "push_delivery_attempts"
    __table_args__ = (
        UniqueConstraint("entry_id", "occurrence_date", "subscription_id", name="uq_push_attempt"),
        Index("ix_push_attempts_status_due", "status", "due_at"),
        Index("ix_push_attempts_user", "user_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    entry_id: Mapped[UUID] = mapped_column(
        ForeignKey("rule_of_life_entries.id", ondelete="CASCADE"),
    )
    subscription_id: Mapped[UUID] = mapped_column(
        ForeignKey("push_subscriptions.id", ondelete="CASCADE"),
    )
    occurrence_date: Mapped[date] = mapped_column()
    due_at: Mapped[datetime] = mapped_column(UTCDateTime())
    status: Mapped[str] = mapped_column(String(12), default="pending")
    attempt_count: Mapped[int] = mapped_column(default=0)
    claimed_until: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # A status code or exception class name only — never an endpoint, key or payload.
    last_error: Mapped[str | None] = mapped_column(String(300))


class RuleOfLifeOccurrence(Base):
    """An occurrence marked completed or skipped: one row per entry and local date."""

    __tablename__ = "rule_of_life_occurrences"
    __table_args__ = (UniqueConstraint("entry_id", "occurrence_date", name="uq_rule_occurrence"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    entry_id: Mapped[UUID] = mapped_column(
        ForeignKey("rule_of_life_entries.id", ondelete="CASCADE"),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    occurrence_date: Mapped[date] = mapped_column()
    status: Mapped[str] = mapped_column(String(10))
    marked_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
