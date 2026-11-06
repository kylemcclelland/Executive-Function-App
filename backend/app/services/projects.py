from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import case, func, select, update
from sqlalchemy.orm import Session

from ..api.dependencies import owned_milestone, owned_project
from ..db import utcnow
from ..models import Milestone, Project, ProjectUpdate, Task, User

HISTORY_LIMIT = 200


def touch_project(db: Session, project_id: UUID | None) -> None:
    """Mark a project as recently worked on so it sorts first when resuming."""
    if project_id is not None:
        db.execute(update(Project).where(Project.id == project_id).values(updated_at=utcnow()))


def next_position(db: Session, project_id: UUID) -> int:
    highest = db.scalar(
        select(func.max(Task.project_position)).where(Task.project_id == project_id)
    )
    return 0 if highest is None else highest + 1


def link_values(
    db: Session, user: User, values: dict,
    current_project: UUID | None = None, current_milestone: UUID | None = None,
) -> dict:
    """Validate project/milestone ownership and derive the dependent task columns."""
    if "project_id" not in values and "milestone_id" not in values:
        return {}
    project_id = values.get("project_id", current_project)
    changes: dict = {"project_id": project_id}
    if project_id != current_project:
        if project_id is not None:
            owned_project(db, user, project_id)
        changes["project_position"] = None if project_id is None else next_position(db, project_id)
        milestone_id = values.get("milestone_id")
    else:
        milestone_id = values.get("milestone_id", current_milestone)
    if milestone_id is not None:
        if project_id is None:
            raise HTTPException(422, "A milestone requires a project")
        owned_milestone(db, user, project_id, milestone_id)
    changes["milestone_id"] = milestone_id
    return changes


def unlink_project_tasks(db: Session, project_id: UUID) -> None:
    db.execute(update(Task).where(Task.project_id == project_id).values(
        project_id=None, milestone_id=None, project_position=None,
    ))


def unlink_milestone_tasks(db: Session, milestone_id: UUID) -> None:
    db.execute(update(Task).where(Task.milestone_id == milestone_id).values(milestone_id=None))


def row_values(instance) -> dict:
    return {column.name: getattr(instance, column.name) for column in instance.__table__.columns}


def project_summaries(db: Session, projects: list[Project]) -> list[dict]:
    if not projects:
        return []
    ids = [project.id for project in projects]
    open_count = dict.fromkeys(ids, 0)
    done_count = dict.fromkeys(ids, 0)
    first_open: dict[UUID, str] = {}
    task_rows = db.execute(
        select(Task.project_id, Task.title, Task.status).where(Task.project_id.in_(ids))
        .order_by(Task.project_position.asc().nulls_last(), Task.created_at, Task.id)
    )
    for project_id, title, status in task_rows:
        if status == "completed":
            done_count[project_id] += 1
        else:
            open_count[project_id] += 1
            first_open.setdefault(project_id, title)
    milestone_counts = {
        project_id: (total, done or 0)
        for project_id, total, done in db.execute(
            select(
                Milestone.project_id, func.count(),
                func.sum(case((Milestone.completed_at.is_not(None), 1), else_=0)),
            ).where(Milestone.project_id.in_(ids)).group_by(Milestone.project_id)
        )
    }
    return [
        {
            **row_values(project),
            "open_task_count": open_count[project.id],
            "completed_task_count": done_count[project.id],
            "milestone_count": milestone_counts.get(project.id, (0, 0))[0],
            "milestones_completed": milestone_counts.get(project.id, (0, 0))[1],
            "next_task_title": first_open.get(project.id),
        }
        for project in projects
    ]


def milestone_summaries(db: Session, milestones: list[Milestone]) -> list[dict]:
    ids = [milestone.id for milestone in milestones]
    counts: dict[UUID, tuple[int, int]] = {}
    if ids:
        counts = {
            milestone_id: (total, done or 0)
            for milestone_id, total, done in db.execute(
                select(
                    Task.milestone_id, func.count(),
                    func.sum(case((Task.status == "completed", 1), else_=0)),
                ).where(Task.milestone_id.in_(ids)).group_by(Task.milestone_id)
            )
        }
    return [
        {
            **row_values(milestone),
            "task_count": counts.get(milestone.id, (0, 0))[0],
            "completed_task_count": counts.get(milestone.id, (0, 0))[1],
        }
        for milestone in milestones
    ]


def project_history(db: Session, project: Project) -> list[dict]:
    entries = [
        {"id": id_, "type": "task_completed", "at": at, "title": title, "next_step": None}
        for id_, title, at in db.execute(
            select(Task.id, Task.title, Task.completed_at).where(
                Task.project_id == project.id, Task.user_id == project.user_id,
                Task.completed_at.is_not(None),
            )
        )
    ]
    entries += [
        {"id": id_, "type": "milestone_completed", "at": at, "title": title, "next_step": None}
        for id_, title, at in db.execute(
            select(Milestone.id, Milestone.title, Milestone.completed_at).where(
                Milestone.project_id == project.id, Milestone.completed_at.is_not(None),
            )
        )
    ]
    entries += [
        {"id": update_.id, "type": update_.kind, "at": update_.created_at,
         "title": update_.summary, "next_step": update_.next_step}
        for update_ in db.scalars(
            select(ProjectUpdate).where(ProjectUpdate.project_id == project.id)
        )
    ]
    entries.sort(key=lambda entry: (entry["at"], str(entry["id"])), reverse=True)
    return entries[:HISTORY_LIMIT]


def active_briefs(db: Session, user: User, limit: int = 3) -> list[dict]:
    projects = db.scalars(
        select(Project).where(
            Project.user_id == user.id, Project.status == "active", Project.archived_at.is_(None),
        ).order_by(Project.updated_at.desc(), Project.id).limit(limit)
    ).all()
    return project_summaries(db, list(projects))
