from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..core.config import DEFAULT_USER_ID
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


def get_user(request: Request, db: DB) -> User:
    settings = request.app.state.settings
    if settings.app_env not in {"development", "test"}:
        raise HTTPException(503, "Authentication is not configured")
    user_id = settings.dev_user_id or DEFAULT_USER_ID
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    db.execute(
        insert(User).values(id=user_id, timezone=settings.dev_user_timezone)
        .on_conflict_do_nothing(index_elements=["id"])
    )
    # Serialize mutations for one identity, including first conversion and daily list replacement.
    return db.scalar(select(User).where(User.id == user_id).with_for_update())


CurrentUser = Annotated[User, Depends(get_user)]


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
