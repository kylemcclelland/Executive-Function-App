from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Content = Annotated[str, StringConstraints(min_length=1, max_length=100000)]
Status = Literal["todo", "in_progress", "in_review", "blocked", "completed"]
TaskKind = Literal["checklist", "board"]
ProjectStatus = Literal["active", "paused", "someday", "completed"]
Intention = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


def blank_to_none(value):
    """Optional text fields treat blank input as "not set"."""
    if isinstance(value, str):
        return value.strip() or None
    return value


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Output(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TaskCreate(Input):
    project_id: UUID | None = None
    milestone_id: UUID | None = None
    title: Title
    description: str | None = Field(default=None, max_length=100000)
    status: Status = "todo"
    task_kind: TaskKind = "checklist"
    due_date: date | None = None
    scheduled_date: date | None = None
    estimated_minutes: int | None = Field(default=None, gt=0, le=525600)
    next_action: str | None = Field(default=None, max_length=100000)
    blocked_reason: str | None = Field(default=None, max_length=2000)
    waiting_on: str | None = Field(default=None, max_length=300)
    blocked_follow_up: date | None = None
    review_notes: str | None = Field(default=None, max_length=10000)
    reviewer_name: str | None = Field(default=None, max_length=200)


class TaskPatch(Input):
    project_id: UUID | None = None
    milestone_id: UUID | None = None
    title: Title | None = None
    description: str | None = Field(default=None, max_length=100000)
    status: Status | None = None
    task_kind: TaskKind | None = None
    due_date: date | None = None
    scheduled_date: date | None = None
    estimated_minutes: int | None = Field(default=None, gt=0, le=525600)
    next_action: str | None = Field(default=None, max_length=100000)
    blocked_reason: str | None = Field(default=None, max_length=2000)
    waiting_on: str | None = Field(default=None, max_length=300)
    blocked_follow_up: date | None = None
    review_notes: str | None = Field(default=None, max_length=10000)
    reviewer_name: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def non_null_required(self):
        for field in ("title", "status", "task_kind"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class StepCreate(Input):
    title: Title
    position: int | None = Field(default=None, ge=0)


class StepPatch(Input):
    title: Title | None = None
    position: int | None = Field(default=None, ge=0)
    is_completed: bool | None = None

    @model_validator(mode="after")
    def non_null_fields(self):
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Step fields cannot be null")
        return self


class StepOut(Output):
    id: UUID
    task_id: UUID
    title: str
    position: int
    is_completed: bool


class TaskOut(Output):
    id: UUID
    user_id: UUID
    project_id: UUID | None
    project_name: str | None
    milestone_id: UUID | None
    project_position: int | None
    title: str
    description: str | None
    status: Status
    task_kind: TaskKind
    due_date: date | None
    scheduled_date: date | None
    estimated_minutes: int | None
    next_action: str | None
    previous_status: Status | None
    blocked_reason: str | None
    waiting_on: str | None
    blocked_follow_up: date | None
    review_notes: str | None
    reviewer_name: str | None
    review_requested_at: datetime | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    steps: list[StepOut]


class InboxCreate(Input):
    content: Content

    @field_validator("content")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Content cannot be blank")
        return value


class InboxPatch(Input):
    content: Content | None = None
    status: Literal["unprocessed", "processed", "archived"] | None = None

    @field_validator("content")
    @classmethod
    def not_blank(cls, value):
        if value is not None and not value.strip():
            raise ValueError("Content cannot be blank")
        return value

    @model_validator(mode="after")
    def non_null_fields(self):
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Inbox fields cannot be null")
        return self


class InboxOut(Output):
    id: UUID
    user_id: UUID
    content: str
    status: Literal["unprocessed", "processed", "archived"]
    converted_task_id: UUID | None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class ConvertInput(Input):
    title: Title | None = None
    task_kind: TaskKind = "checklist"   # where the idea goes: the Daily Checklist or the Task Board


class PrioritiesInput(Input):
    task_ids: list[UUID] = Field(max_length=3)

    @field_validator("task_ids")
    @classmethod
    def unique_tasks(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("Priorities must be unique")
        return value


class ProjectBrief(Output):
    id: UUID
    name: str
    next_action: str | None
    next_task_title: str | None
    open_task_count: int


class TodayOut(Output):
    date: date
    timezone: str
    priorities: list[TaskOut]
    previous_tasks: list[TaskOut]
    completed_tasks: list[TaskOut]
    inbox_count: int
    active_projects: list[ProjectBrief] = []


class ProjectCreate(Input):
    name: Title
    description: str | None = Field(default=None, max_length=100000)
    category: str | None = Field(default=None, max_length=100)
    status: ProjectStatus = "active"
    target_date: date | None = None
    next_action: str | None = Field(default=None, max_length=2000)

    _blank = field_validator("description", "category", "next_action", mode="before")(blank_to_none)


class ProjectPatch(Input):
    name: Title | None = None
    description: str | None = Field(default=None, max_length=100000)
    category: str | None = Field(default=None, max_length=100)
    status: ProjectStatus | None = None
    target_date: date | None = None
    next_action: str | None = Field(default=None, max_length=2000)
    archived: bool | None = None

    _blank = field_validator("description", "category", "next_action", mode="before")(blank_to_none)

    @model_validator(mode="after")
    def non_null_required(self):
        for field in ("name", "status", "archived"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class ProjectOut(Output):
    id: UUID
    user_id: UUID
    name: str
    description: str | None
    category: str | None
    status: ProjectStatus
    target_date: date | None
    next_action: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    archived_at: datetime | None
    open_task_count: int
    completed_task_count: int
    milestone_count: int
    milestones_completed: int
    next_task_title: str | None


class ProjectUpdateCreate(Input):
    kind: Literal["progress", "session"] = "session"
    summary: Content
    next_step: str | None = Field(default=None, max_length=2000)

    _blank = field_validator("next_step", mode="before")(blank_to_none)

    @field_validator("summary")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Summary cannot be blank")
        return value.strip()


class ProjectUpdateOut(Output):
    id: UUID
    project_id: UUID
    kind: Literal["progress", "session"]
    summary: str
    next_step: str | None
    created_at: datetime


class WorkSessionCreate(Input):
    project_id: UUID
    task_id: UUID | None = None
    intention: Intention
    planned_minutes: int | None = Field(default=None, gt=0, le=480)


class WorkSessionFinish(Input):
    accomplished: str | None = Field(default=None, max_length=100000)
    resume_note: str | None = Field(default=None, max_length=100000)
    interrupted: bool = False

    _blank = field_validator("accomplished", "resume_note", mode="before")(blank_to_none)


class WorkSessionOut(Output):
    id: UUID
    project_id: UUID
    project_name: str
    task_id: UUID | None
    task_title: str | None
    intention: str
    status: Literal["active", "finished", "interrupted"]
    started_at: datetime
    ended_at: datetime | None
    planned_minutes: int | None
    elapsed_seconds: int | None
    accomplished: str | None
    resume_note: str | None


class ProjectDetailOut(ProjectOut):
    last_update: ProjectUpdateOut | None
    last_session: WorkSessionOut | None = None
    resume_session: WorkSessionOut | None = None


class ProjectTaskIds(Input):
    task_ids: list[UUID] = Field(max_length=500)

    @field_validator("task_ids")
    @classmethod
    def unique_tasks(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("Tasks must be unique")
        return value


class MilestoneCreate(Input):
    title: Title
    description: str | None = Field(default=None, max_length=100000)
    target_date: date | None = None

    _blank = field_validator("description", mode="before")(blank_to_none)


class MilestonePatch(Input):
    title: Title | None = None
    description: str | None = Field(default=None, max_length=100000)
    target_date: date | None = None
    completed: bool | None = None

    _blank = field_validator("description", mode="before")(blank_to_none)

    @model_validator(mode="after")
    def non_null_required(self):
        for field in ("title", "completed"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class MilestoneOut(Output):
    id: UUID
    project_id: UUID
    title: str
    description: str | None
    target_date: date | None
    position: int
    completed_at: datetime | None
    task_count: int
    completed_task_count: int


class NoteCreate(Input):
    title: Title | None = None
    content: Content

    _blank = field_validator("title", mode="before")(blank_to_none)

    @field_validator("content")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Content cannot be blank")
        return value


class NotePatch(Input):
    title: Title | None = None
    content: Content | None = None

    _blank = field_validator("title", mode="before")(blank_to_none)

    @field_validator("content")
    @classmethod
    def not_blank(cls, value):
        if value is not None and not value.strip():
            raise ValueError("Content cannot be blank")
        return value

    @model_validator(mode="after")
    def content_not_null(self):
        if "content" in self.model_fields_set and self.content is None:
            raise ValueError("content cannot be null")
        return self


class NoteOut(Output):
    id: UUID
    project_id: UUID
    title: str | None
    content: str
    created_at: datetime
    updated_at: datetime


class HistoryEntry(Output):
    id: UUID
    type: Literal["task_completed", "milestone_completed", "progress", "session"]
    at: datetime
    title: str
    next_step: str | None = None


class UserPatch(Input):
    timezone: str

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ValueError("Unknown IANA timezone") from exc
        return value


class UserOut(Output):
    id: UUID
    timezone: str
    created_at: datetime
    updated_at: datetime
