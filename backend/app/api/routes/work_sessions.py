from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ... import schemas as s
from ...db import utcnow
from ...models import WorkSession
from ...services.projects import touch_project
from ..dependencies import DB, CurrentUser, owned_project, owned_task, owned_work_session

router = APIRouter()

SESSION_LIST_LIMIT = 50


@router.get("/api/work-sessions/active", response_model=s.WorkSessionOut | None)
def read_active_session(db: DB, user: CurrentUser):
    """The session in progress, recovered from its stored start time, or null."""
    return db.scalar(select(WorkSession).where(
        WorkSession.user_id == user.id, WorkSession.status == "active",
    ))


@router.post("/api/work-sessions", response_model=s.WorkSessionOut, status_code=201)
def begin_session(body: s.WorkSessionCreate, db: DB, user: CurrentUser):
    project = owned_project(db, user, body.project_id)
    if body.task_id is not None and owned_task(db, user, body.task_id).project_id != project.id:
        raise HTTPException(422, "That task does not belong to this project")
    already_active = db.scalar(select(WorkSession.id).where(
        WorkSession.user_id == user.id, WorkSession.status == "active",
    ))
    if already_active is not None:
        raise HTTPException(409, "A work session is already in progress")
    work_session = WorkSession(
        **body.model_dump(), user_id=user.id, status="active", started_at=utcnow(),
    )
    db.add(work_session)
    touch_project(db, project.id)
    try:
        db.flush()
    except IntegrityError as exc:  # lost a race with another request; the index is the backstop
        raise HTTPException(409, "A work session is already in progress") from exc
    return work_session


@router.get("/api/work-sessions/{session_id}", response_model=s.WorkSessionOut)
def read_session(session_id: UUID, db: DB, user: CurrentUser):
    return owned_work_session(db, user, session_id)


@router.post("/api/work-sessions/{session_id}/finish", response_model=s.WorkSessionOut)
def finish_session(session_id: UUID, body: s.WorkSessionFinish, db: DB, user: CurrentUser):
    work_session = owned_work_session(db, user, session_id)
    if work_session.status != "active":
        raise HTTPException(409, "This session has already ended")
    if body.interrupted:
        # The real end is unknown, so no end time or duration is invented.
        work_session.status = "interrupted"
    else:
        now = utcnow()
        work_session.status = "finished"
        work_session.ended_at = now
        work_session.elapsed_seconds = max(0, int((now - work_session.started_at).total_seconds()))
    work_session.accomplished = body.accomplished
    work_session.resume_note = body.resume_note
    touch_project(db, work_session.project_id)
    db.flush()
    return work_session


@router.get("/api/projects/{project_id}/work-sessions", response_model=list[s.WorkSessionOut])
def list_project_sessions(project_id: UUID, db: DB, user: CurrentUser):
    owned_project(db, user, project_id)
    return db.scalars(
        select(WorkSession).where(
            WorkSession.project_id == project_id, WorkSession.user_id == user.id,
            WorkSession.status != "active",
        ).order_by(WorkSession.started_at.desc(), WorkSession.id.desc()).limit(SESSION_LIST_LIMIT)
    ).all()
