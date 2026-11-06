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
Status = Literal["todo", "in_progress", "completed"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Output(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TaskCreate(Input):
    project_id: UUID | None = None
    title: Title
    description: str | None = Field(default=None, max_length=100000)
    status: Status = "todo"
    due_date: date | None = None
    scheduled_date: date | None = None
    estimated_minutes: int | None = Field(default=None, gt=0, le=525600)
    next_action: str | None = Field(default=None, max_length=100000)


class TaskPatch(Input):
    project_id: UUID | None = None
    title: Title | None = None
    description: str | None = Field(default=None, max_length=100000)
    status: Status | None = None
    due_date: date | None = None
    scheduled_date: date | None = None
    estimated_minutes: int | None = Field(default=None, gt=0, le=525600)
    next_action: str | None = Field(default=None, max_length=100000)

    @model_validator(mode="after")
    def non_null_required(self):
        for field in ("title", "status"):
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
    title: str
    description: str | None
    status: Status
    due_date: date | None
    scheduled_date: date | None
    estimated_minutes: int | None
    next_action: str | None
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


class PrioritiesInput(Input):
    task_ids: list[UUID] = Field(max_length=3)

    @field_validator("task_ids")
    @classmethod
    def unique_tasks(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("Priorities must be unique")
        return value


class TodayOut(Output):
    date: date
    timezone: str
    priorities: list[TaskOut]
    previous_tasks: list[TaskOut]
    completed_tasks: list[TaskOut]
    inbox_count: int


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
