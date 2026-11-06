from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import delete, select, text

from ... import schemas as s
from ...db import utcnow
from ...models import DailyPriority, InboxItem, Step, Task
from ...services.projects import link_values, touch_project
from ...services.today import today_view
from ..dependencies import DB, CurrentUser, owned_inbox, owned_step, owned_task
from .books import router as books_router
from .notes import router as notes_router
from .projects import router as projects_router
from .work_sessions import router as work_sessions_router

router = APIRouter()
router.include_router(projects_router)
router.include_router(books_router)
router.include_router(notes_router)
router.include_router(work_sessions_router)


@router.get("/health")
def health(db: DB):
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(503, "Database unavailable") from exc
    return {"status": "ok"}


@router.get("/api/user", response_model=s.UserOut)
def read_user(user: CurrentUser):
    return user


@router.patch("/api/user", response_model=s.UserOut)
def update_user(body: s.UserPatch, db: DB, user: CurrentUser):
    user.timezone = body.timezone
    db.flush()
    return user


@router.get("/api/tasks", response_model=list[s.TaskOut])
def list_tasks(db: DB, user: CurrentUser, status: s.Status | None = None):
    statement = select(Task).where(Task.user_id == user.id)
    if status is not None:
        statement = statement.where(Task.status == status)
    return db.scalars(statement.order_by(Task.created_at.desc(), Task.id)).all()


@router.post("/api/tasks", response_model=s.TaskOut, status_code=201)
def create_task(body: s.TaskCreate, db: DB, user: CurrentUser):
    values = body.model_dump()
    values.update(link_values(db, user, values))
    task = Task(
        **values, user_id=user.id,
        completed_at=utcnow() if body.status == "completed" else None,
    )
    db.add(task)
    touch_project(db, task.project_id)
    db.flush()
    db.refresh(task, ["project"])
    return task


@router.get("/api/tasks/{task_id}", response_model=s.TaskOut)
def read_task(task_id: UUID, db: DB, user: CurrentUser):
    return owned_task(db, user, task_id)


@router.patch("/api/tasks/{task_id}", response_model=s.TaskOut)
def update_task(task_id: UUID, body: s.TaskPatch, db: DB, user: CurrentUser):
    task = owned_task(db, user, task_id)
    values = body.model_dump(exclude_unset=True)
    if "status" in values and values["status"] != task.status:
        task.completed_at = utcnow() if values["status"] == "completed" else None
    previous_project = task.project_id
    values.update(link_values(db, user, values, task.project_id, task.milestone_id))
    for key, value in values.items():
        setattr(task, key, value)
    touch_project(db, previous_project)
    touch_project(db, task.project_id)
    db.flush()
    db.refresh(task, ["project"])
    return task


@router.delete("/api/tasks/{task_id}", status_code=204)
def delete_task(task_id: UUID, db: DB, user: CurrentUser):
    db.delete(owned_task(db, user, task_id))
    db.flush()
    return Response(status_code=204)


@router.post("/api/tasks/{task_id}/steps", response_model=s.StepOut, status_code=201)
def create_step(task_id: UUID, body: s.StepCreate, db: DB, user: CurrentUser):
    task = owned_task(db, user, task_id)
    steps = list(task.steps)
    position = len(steps) if body.position is None else min(body.position, len(steps))
    step = Step(title=body.title, position=position, task=task)
    steps.insert(position, step)
    for index, item in enumerate(steps):
        item.position = index
    task.updated_at = utcnow()
    db.add(step)
    db.flush()
    return step


@router.patch("/api/tasks/{task_id}/steps/{step_id}", response_model=s.StepOut)
def update_step(
    task_id: UUID, step_id: UUID, body: s.StepPatch, db: DB, user: CurrentUser,
):
    task, step = owned_step(db, user, task_id, step_id)
    values = body.model_dump(exclude_unset=True)
    if "position" in values:
        steps = [item for item in task.steps if item.id != step_id]
        steps.insert(min(values.pop("position"), len(steps)), step)
        for index, item in enumerate(steps):
            item.position = index
    for key, value in values.items():
        setattr(step, key, value)
    task.updated_at = utcnow()
    db.flush()
    return step


@router.delete("/api/tasks/{task_id}/steps/{step_id}", status_code=204)
def delete_step(task_id: UUID, step_id: UUID, db: DB, user: CurrentUser):
    task, step = owned_step(db, user, task_id, step_id)
    remaining = [item for item in task.steps if item.id != step_id]
    db.delete(step)
    for index, item in enumerate(remaining):
        item.position = index
    task.updated_at = utcnow()
    db.flush()
    return Response(status_code=204)


@router.get("/api/inbox", response_model=list[s.InboxOut])
def list_inbox(
    db: DB, user: CurrentUser,
    status: Annotated[
        str | None, Query(pattern="^(unprocessed|processed|archived)$")
    ] = None,
):
    statement = select(InboxItem).where(InboxItem.user_id == user.id)
    if status is not None:
        statement = statement.where(InboxItem.status == status)
    return db.scalars(statement.order_by(InboxItem.created_at.desc(), InboxItem.id)).all()


@router.post("/api/inbox", response_model=s.InboxOut, status_code=201)
def create_inbox(body: s.InboxCreate, db: DB, user: CurrentUser):
    item = InboxItem(content=body.content, user_id=user.id)
    db.add(item)
    db.flush()
    return item


@router.get("/api/inbox/{item_id}", response_model=s.InboxOut)
def read_inbox(item_id: UUID, db: DB, user: CurrentUser):
    return owned_inbox(db, user, item_id)


@router.patch("/api/inbox/{item_id}", response_model=s.InboxOut)
def update_inbox(item_id: UUID, body: s.InboxPatch, db: DB, user: CurrentUser):
    item = owned_inbox(db, user, item_id)
    values = body.model_dump(exclude_unset=True)
    if item.was_converted and "content" in values:
        raise HTTPException(409, "Processed captures are immutable")
    if values.get("status") == "processed" and not item.was_converted:
        raise HTTPException(409, "Only converted captures can be processed")
    if values.get("status") == "unprocessed" and item.was_converted:
        values["status"] = "processed"
    for key, value in values.items():
        setattr(item, key, value)
    if "status" in values:
        item.archived_at = utcnow() if item.status == "archived" else None
    db.flush()
    return item


@router.delete("/api/inbox/{item_id}", status_code=204)
def delete_inbox(item_id: UUID, db: DB, user: CurrentUser):
    db.delete(owned_inbox(db, user, item_id))
    db.flush()
    return Response(status_code=204)


@router.post("/api/inbox/{item_id}/convert", response_model=s.TaskOut, include_in_schema=False)
@router.post("/api/inbox/{item_id}/convert-to-task", response_model=s.TaskOut)
def convert_inbox(
    item_id: UUID, db: DB, user: CurrentUser, body: s.ConvertInput | None = None,
):
    item = owned_inbox(db, user, item_id)
    if item.converted_task_id is not None:
        return owned_task(db, user, item.converted_task_id)
    if item.was_converted:
        raise HTTPException(409, "The converted task was deleted")
    if item.status == "archived":
        raise HTTPException(409, "Restore the capture before conversion")
    task = Task(
        user_id=user.id,
        title=(body.title if body and body.title else item.content.strip()[:300]),
        description=item.content,
    )
    db.add(task)
    db.flush()
    item.converted_task_id = task.id
    item.was_converted = True
    item.status = "processed"
    db.flush()
    return task


@router.get("/api/today", response_model=s.TodayOut)
def get_today(db: DB, user: CurrentUser):
    return today_view(db, user)


@router.put("/api/today/priorities", response_model=s.TodayOut)
def put_priorities(body: s.PrioritiesInput, db: DB, user: CurrentUser):
    for task_id in body.task_ids:
        owned_task(db, user, task_id)
    today = utcnow().astimezone(ZoneInfo(user.timezone)).date()
    db.execute(delete(DailyPriority).where(
        DailyPriority.user_id == user.id, DailyPriority.priority_date == today,
    ))
    db.add_all([
        DailyPriority(user_id=user.id, priority_date=today, task_id=task_id, position=index)
        for index, task_id in enumerate(body.task_ids)
    ])
    db.flush()
    return today_view(db, user)
