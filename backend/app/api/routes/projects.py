from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import func, select

from ... import schemas as s
from ...db import utcnow
from ...models import Milestone, Project, ProjectNote, ProjectUpdate, Task, WorkSession
from ...services.projects import (
    milestone_summaries,
    next_position,
    project_history,
    project_summaries,
    touch_project,
    unlink_milestone_tasks,
    unlink_project_tasks,
)
from ..dependencies import DB, CurrentUser, owned_milestone, owned_note, owned_project, owned_task

router = APIRouter(prefix="/api/projects")


def like_pattern(term: str) -> str:
    escaped = term.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def detail(db, project: Project) -> dict:
    last_update = db.scalar(
        select(ProjectUpdate).where(ProjectUpdate.project_id == project.id)
        .order_by(ProjectUpdate.created_at.desc(), ProjectUpdate.id.desc()).limit(1)
    )
    ended = WorkSession.project_id == project.id, WorkSession.status != "active"
    latest = select(WorkSession).where(*ended).order_by(
        WorkSession.started_at.desc(), WorkSession.id.desc(),
    ).limit(1)
    return {
        **project_summaries(db, [project])[0], "last_update": last_update,
        "last_session": db.scalar(latest),
        "resume_session": db.scalar(latest.where(WorkSession.resume_note.is_not(None))),
    }


def apply_status(project: Project, status: str) -> None:
    if status != project.status:
        project.completed_at = utcnow() if status == "completed" else None
    project.status = status


@router.get("", response_model=list[s.ProjectOut])
def list_projects(
    db: DB, user: CurrentUser, status: s.ProjectStatus | None = None,
    q: Annotated[str | None, Query(max_length=200)] = None, archived: bool = False,
):
    statement = select(Project).where(Project.user_id == user.id)
    statement = statement.where(
        Project.archived_at.is_not(None) if archived else Project.archived_at.is_(None)
    )
    if status is not None:
        statement = statement.where(Project.status == status)
    if q and q.strip():
        pattern = like_pattern(q)
        statement = statement.where(
            func.lower(Project.name).like(pattern, escape="\\")
            | func.lower(func.coalesce(Project.description, "")).like(pattern, escape="\\")
            | func.lower(func.coalesce(Project.category, "")).like(pattern, escape="\\")
        )
    projects = db.scalars(statement.order_by(Project.updated_at.desc(), Project.id)).all()
    return project_summaries(db, list(projects))


@router.post("", response_model=s.ProjectDetailOut, status_code=201)
def create_project(body: s.ProjectCreate, db: DB, user: CurrentUser):
    values = body.model_dump()
    project = Project(**values, user_id=user.id)
    if body.status == "completed":
        project.completed_at = utcnow()
    db.add(project)
    db.flush()
    return detail(db, project)


@router.get("/{project_id}", response_model=s.ProjectDetailOut)
def read_project(project_id: UUID, db: DB, user: CurrentUser):
    return detail(db, owned_project(db, user, project_id))


@router.patch("/{project_id}", response_model=s.ProjectDetailOut)
def update_project(project_id: UUID, body: s.ProjectPatch, db: DB, user: CurrentUser):
    project = owned_project(db, user, project_id)
    values = body.model_dump(exclude_unset=True)
    if "status" in values:
        apply_status(project, values.pop("status"))
    if "archived" in values:
        archived = values.pop("archived")
        if archived and project.archived_at is None:
            project.archived_at = utcnow()
        elif not archived:
            project.archived_at = None
    for key, value in values.items():
        setattr(project, key, value)
    project.updated_at = utcnow()
    db.flush()
    return detail(db, project)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: UUID, db: DB, user: CurrentUser):
    project = owned_project(db, user, project_id)
    # Deleting a project never deletes the user's tasks; they simply become unassigned.
    unlink_project_tasks(db, project.id)
    db.delete(project)
    db.flush()
    return Response(status_code=204)


@router.get("/{project_id}/tasks", response_model=list[s.TaskOut])
def list_project_tasks(project_id: UUID, db: DB, user: CurrentUser):
    owned_project(db, user, project_id)
    return db.scalars(
        select(Task).where(Task.project_id == project_id, Task.user_id == user.id)
        .order_by(Task.project_position.asc().nulls_last(), Task.created_at, Task.id)
    ).all()


@router.post("/{project_id}/tasks", response_model=list[s.TaskOut])
def assign_tasks(project_id: UUID, body: s.ProjectTaskIds, db: DB, user: CurrentUser):
    """Link existing tasks to this project; tasks are never copied."""
    project = owned_project(db, user, project_id)
    tasks = [owned_task(db, user, task_id) for task_id in body.task_ids]
    position = next_position(db, project.id)
    for task in tasks:
        if task.project_id != project.id:
            touch_project(db, task.project_id)
            task.project_id = project.id
            task.milestone_id = None
            task.project_position = position
            position += 1
    touch_project(db, project.id)
    db.flush()
    for task in tasks:
        db.refresh(task, ["project"])
    return list_project_tasks(project_id, db, user)


@router.put("/{project_id}/tasks/order", response_model=list[s.TaskOut])
def reorder_tasks(project_id: UUID, body: s.ProjectTaskIds, db: DB, user: CurrentUser):
    owned_project(db, user, project_id)
    tasks = db.scalars(
        select(Task).where(Task.project_id == project_id, Task.user_id == user.id)
        .order_by(Task.project_position.asc().nulls_last(), Task.created_at, Task.id)
    ).all()
    by_id = {task.id: task for task in tasks}
    if any(task_id not in by_id for task_id in body.task_ids):
        raise HTTPException(404, "Task not found in this project")
    listed = [by_id[task_id] for task_id in body.task_ids]
    for position, task in enumerate(listed + [t for t in tasks if t.id not in set(body.task_ids)]):
        task.project_position = position
    db.flush()
    return list_project_tasks(project_id, db, user)


@router.get("/{project_id}/milestones", response_model=list[s.MilestoneOut])
def list_milestones(project_id: UUID, db: DB, user: CurrentUser):
    owned_project(db, user, project_id)
    milestones = db.scalars(
        select(Milestone).where(Milestone.project_id == project_id)
        .order_by(Milestone.position, Milestone.created_at, Milestone.id)
    ).all()
    return milestone_summaries(db, list(milestones))


@router.post("/{project_id}/milestones", response_model=s.MilestoneOut, status_code=201)
def create_milestone(project_id: UUID, body: s.MilestoneCreate, db: DB, user: CurrentUser):
    owned_project(db, user, project_id)
    position = db.scalar(
        select(func.max(Milestone.position)).where(Milestone.project_id == project_id)
    )
    milestone = Milestone(
        **body.model_dump(), project_id=project_id, user_id=user.id,
        position=0 if position is None else position + 1,
    )
    db.add(milestone)
    touch_project(db, project_id)
    db.flush()
    return milestone_summaries(db, [milestone])[0]


@router.patch("/{project_id}/milestones/{milestone_id}", response_model=s.MilestoneOut)
def update_milestone(
    project_id: UUID, milestone_id: UUID, body: s.MilestonePatch, db: DB, user: CurrentUser,
):
    owned_project(db, user, project_id)
    milestone = owned_milestone(db, user, project_id, milestone_id)
    values = body.model_dump(exclude_unset=True)
    if "completed" in values:
        completed = values.pop("completed")
        if completed and milestone.completed_at is None:
            milestone.completed_at = utcnow()
        elif not completed:
            milestone.completed_at = None
    for key, value in values.items():
        setattr(milestone, key, value)
    touch_project(db, project_id)
    db.flush()
    return milestone_summaries(db, [milestone])[0]


@router.delete("/{project_id}/milestones/{milestone_id}", status_code=204)
def delete_milestone(project_id: UUID, milestone_id: UUID, db: DB, user: CurrentUser):
    owned_project(db, user, project_id)
    milestone = owned_milestone(db, user, project_id, milestone_id)
    unlink_milestone_tasks(db, milestone.id)
    db.delete(milestone)
    db.flush()
    return Response(status_code=204)


@router.get("/{project_id}/notes", response_model=list[s.NoteOut])
def list_notes(
    project_id: UUID, db: DB, user: CurrentUser,
    q: Annotated[str | None, Query(max_length=200)] = None,
):
    owned_project(db, user, project_id)
    statement = select(ProjectNote).where(
        ProjectNote.project_id == project_id, ProjectNote.user_id == user.id,
    )
    if q and q.strip():
        pattern = like_pattern(q)
        statement = statement.where(
            func.lower(ProjectNote.content).like(pattern, escape="\\")
            | func.lower(func.coalesce(ProjectNote.title, "")).like(pattern, escape="\\")
        )
    return db.scalars(statement.order_by(ProjectNote.updated_at.desc(), ProjectNote.id)).all()


@router.post("/{project_id}/notes", response_model=s.NoteOut, status_code=201)
def create_note(project_id: UUID, body: s.NoteCreate, db: DB, user: CurrentUser):
    owned_project(db, user, project_id)
    note = ProjectNote(**body.model_dump(), project_id=project_id, user_id=user.id)
    db.add(note)
    touch_project(db, project_id)
    db.flush()
    return note


@router.patch("/{project_id}/notes/{note_id}", response_model=s.NoteOut)
def update_note(project_id: UUID, note_id: UUID, body: s.NotePatch, db: DB, user: CurrentUser):
    owned_project(db, user, project_id)
    note = owned_note(db, user, project_id, note_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(note, key, value)
    touch_project(db, project_id)
    db.flush()
    return note


@router.delete("/{project_id}/notes/{note_id}", status_code=204)
def delete_note(project_id: UUID, note_id: UUID, db: DB, user: CurrentUser):
    owned_project(db, user, project_id)
    db.delete(owned_note(db, user, project_id, note_id))
    db.flush()
    return Response(status_code=204)


@router.get("/{project_id}/updates", response_model=list[s.ProjectUpdateOut])
def list_updates(project_id: UUID, db: DB, user: CurrentUser):
    owned_project(db, user, project_id)
    return db.scalars(
        select(ProjectUpdate).where(
            ProjectUpdate.project_id == project_id, ProjectUpdate.user_id == user.id,
        ).order_by(ProjectUpdate.created_at.desc(), ProjectUpdate.id.desc())
    ).all()


@router.post("/{project_id}/updates", response_model=s.ProjectUpdateOut, status_code=201)
def create_update(project_id: UUID, body: s.ProjectUpdateCreate, db: DB, user: CurrentUser):
    """Record progress or a work session. A stated next step becomes the project's next action."""
    project = owned_project(db, user, project_id)
    update = ProjectUpdate(**body.model_dump(), project_id=project_id, user_id=user.id)
    db.add(update)
    if body.next_step:
        project.next_action = body.next_step
    project.updated_at = utcnow()
    db.flush()
    return update


@router.delete("/{project_id}/updates/{update_id}", status_code=204)
def delete_update(project_id: UUID, update_id: UUID, db: DB, user: CurrentUser):
    owned_project(db, user, project_id)
    update = db.scalar(select(ProjectUpdate).where(
        ProjectUpdate.id == update_id, ProjectUpdate.project_id == project_id,
        ProjectUpdate.user_id == user.id,
    ))
    if update is None:
        raise HTTPException(404, "Update not found")
    db.delete(update)
    db.flush()
    return Response(status_code=204)


@router.get("/{project_id}/history", response_model=list[s.HistoryEntry])
def read_history(project_id: UUID, db: DB, user: CurrentUser):
    return project_history(db, owned_project(db, user, project_id))
