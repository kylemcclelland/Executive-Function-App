from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import utcnow
from ..models import DailyPriority, InboxItem, Task, User


def today_view(db: Session, user: User) -> dict:
    zone = ZoneInfo(user.timezone)
    today = utcnow().astimezone(zone).date()
    start = datetime.combine(today, time.min, tzinfo=zone).astimezone(UTC)
    end = datetime.combine(today + timedelta(days=1), time.min, tzinfo=zone).astimezone(UTC)
    priority_ids = select(DailyPriority.task_id).where(
        DailyPriority.user_id == user.id, DailyPriority.priority_date == today,
    )
    priorities = db.scalars(
        select(Task).join(DailyPriority, DailyPriority.task_id == Task.id).where(
            Task.user_id == user.id, DailyPriority.user_id == user.id,
            DailyPriority.priority_date == today,
        ).order_by(DailyPriority.position)
    ).all()
    past_priority_ids = select(DailyPriority.task_id).where(
        DailyPriority.user_id == user.id, DailyPriority.priority_date < today,
    )
    previous = db.scalars(
        select(Task).where(
            Task.user_id == user.id, Task.status != "completed",
            Task.id.not_in(priority_ids),
            or_(Task.scheduled_date < today, Task.id.in_(past_priority_ids)),
        ).order_by(Task.scheduled_date.asc().nulls_last(), Task.created_at, Task.id)
    ).all()
    completed = db.scalars(
        select(Task).where(
            Task.user_id == user.id, Task.status == "completed",
            Task.completed_at >= start, Task.completed_at < end,
        ).order_by(Task.completed_at, Task.id)
    ).all()
    inbox_count = db.scalar(
        select(func.count()).select_from(InboxItem).where(
            InboxItem.user_id == user.id, InboxItem.status == "unprocessed",
        )
    )
    return {
        "date": today, "timezone": user.timezone, "priorities": priorities,
        "previous_tasks": previous, "completed_tasks": completed, "inbox_count": inbox_count,
    }
