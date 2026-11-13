from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..models import (
    Book,
    InboxItem,
    Milestone,
    Note,
    NoteLink,
    Project,
    ProjectNote,
    Step,
    Task,
    User,
    WorkSession,
)


def get_session(request: Request):
    with request.app.state.session_factory() as session:
        with session.begin():
            yield session


DB = Annotated[Session, Depends(get_session, scope="function")]


def require_authentication(request: Request) -> str:
    """The verified Clerk user id for this request; rejects anything unauthenticated.

    Applied to every protected router, so a new endpoint is protected without having to remember.
    Verified once per request; the token is the only source of identity.
    """
    clerk_user_id = getattr(request.state, "clerk_user_id", None)
    if clerk_user_id is None:
        authenticate = request.app.state.authenticator
        if authenticate is None:
            raise HTTPException(503, "Authentication is not configured")
        clerk_user_id = request.state.clerk_user_id = authenticate(request)
    return clerk_user_id


def ensure_user(db: Session, clerk_user_id: str, timezone: str) -> User:
    """The account for a verified Clerk user, created empty on first sight.

    Accounts are looked up by ``clerk_user_id`` only. The legacy pre-authentication user has none,
    so a new sign-up can never be matched to (or see) data that existed before authentication.
    """
    # Serialize mutations for one identity, including first conversion and daily list replacement.
    statement = select(User).where(User.clerk_user_id == clerk_user_id).with_for_update()
    user = db.scalar(statement)
    if user is None:
        insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
        db.execute(
            insert(User).values(id=uuid4(), clerk_user_id=clerk_user_id, timezone=timezone)
            .on_conflict_do_nothing(index_elements=["clerk_user_id"])
        )
        user = db.scalar(statement)
    return user


def current_user_id(request: Request) -> UUID:
    """The authenticated user's id, via its own short transaction (for handlers with no session)."""
    clerk_user_id = require_authentication(request)
    with request.app.state.session_factory() as session, session.begin():
        return ensure_user(session, clerk_user_id, request.app.state.settings.dev_user_timezone).id


def get_user(request: Request, db: DB) -> User:
    return ensure_user(
        db, require_authentication(request), request.app.state.settings.dev_user_timezone,
    )


CurrentUser = Annotated[User, Depends(get_user)]


def require_owner(request: Request, db: DB) -> User:
    """The application's one configured owner; everyone else is 403.

    Ownership is the server-side OWNER_CLERK_USER_ID setting compared with the verified token's
    stable Clerk id — never an email, a request field, or "the first user". Unset means closed:
    with no owner configured, no account (not even a signed-in one) has editorial access.
    """
    user = get_user(request, db)
    owner = request.app.state.settings.owner_clerk_user_id
    if not owner or user.clerk_user_id != owner:
        raise HTTPException(403, "Editorial access is restricted to the owner")
    return user


Owner = Annotated[User, Depends(require_owner)]


def owned_task(db: Session, user: User, task_id: UUID) -> Task:
    task = db.scalar(select(Task).where(Task.id == task_id, Task.user_id == user.id))
    if task is None:
        raise HTTPException(404, "Task not found")
    return task


def owned_inbox(db: Session, user: User, item_id: UUID) -> InboxItem:
    item = db.scalar(
        select(InboxItem).where(InboxItem.id == item_id, InboxItem.user_id == user.id)
    )
    if item is None:
        raise HTTPException(404, "Inbox item not found")
    return item


def owned_step(db: Session, user: User, task_id: UUID, step_id: UUID) -> tuple[Task, Step]:
    task = owned_task(db, user, task_id)
    step = next((step for step in task.steps if step.id == step_id), None)
    if step is None:
        raise HTTPException(404, "Step not found")
    return task, step


def owned_project(db: Session, user: User, project_id: UUID) -> Project:
    project = db.scalar(
        select(Project).where(Project.id == project_id, Project.user_id == user.id)
    )
    if project is None:
        raise HTTPException(404, "Project not found")
    return project


def owned_milestone(db: Session, user: User, project_id: UUID, milestone_id: UUID) -> Milestone:
    milestone = db.scalar(select(Milestone).where(
        Milestone.id == milestone_id, Milestone.project_id == project_id,
        Milestone.user_id == user.id,
    ))
    if milestone is None:
        raise HTTPException(404, "Milestone not found")
    return milestone


def owned_note(db: Session, user: User, project_id: UUID, note_id: UUID) -> ProjectNote:
    note = db.scalar(select(ProjectNote).where(
        ProjectNote.id == note_id, ProjectNote.project_id == project_id,
        ProjectNote.user_id == user.id,
    ))
    if note is None:
        raise HTTPException(404, "Note not found")
    return note


def owned_work_session(db: Session, user: User, session_id: UUID) -> WorkSession:
    work_session = db.scalar(
        select(WorkSession).where(WorkSession.id == session_id, WorkSession.user_id == user.id)
    )
    if work_session is None:
        raise HTTPException(404, "Work session not found")
    return work_session


def owned_book(db: Session, user: User, book_id: UUID) -> Book:
    book = db.scalar(select(Book).where(Book.id == book_id, Book.user_id == user.id))
    if book is None:
        raise HTTPException(404, "Book not found")
    return book


def owned_library_note(db: Session, user: User, note_id: UUID) -> Note:
    note = db.scalar(select(Note).where(Note.id == note_id, Note.user_id == user.id))
    if note is None:
        raise HTTPException(404, "Note not found")
    return note


def owned_note_link(db: Session, user: User, link_id: UUID) -> NoteLink:
    link = db.scalar(select(NoteLink).where(NoteLink.id == link_id, NoteLink.user_id == user.id))
    if link is None:
        raise HTTPException(404, "Connection not found")
    return link
