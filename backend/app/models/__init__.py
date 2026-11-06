from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base, UTCDateTime, utcnow


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class User(Timestamps, Base):
    __tablename__ = "users"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
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
    project_id: Mapped[UUID | None]
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
