from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..core.config import DEFAULT_USER_ID
from ..models import InboxItem, Step, Task, User


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
