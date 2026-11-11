# ruff: noqa: E501
from datetime import date
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import delete, select

from ...db import utcnow
from ...models import RuleOfLifeEntry, RuleOfLifeOccurrence
from ...services import rule_of_life as rol
from ..dependencies import DB, CurrentUser

# Rule of Life: the signed-in user's scheduled prayers. Only the user's own entries are ever visible (another user's id is a 404).
router = APIRouter(prefix="/api/rule-of-life", tags=["rule-of-life"])


@router.get("", response_model=list[rol.EntryOut])
def list_entries(db: DB, user: CurrentUser):
    entries = db.scalars(select(RuleOfLifeEntry).where(RuleOfLifeEntry.user_id == user.id).order_by(RuleOfLifeEntry.local_time, RuleOfLifeEntry.title))
    return [rol.out(db, user, entry) for entry in entries]


@router.get("/notifications")
def notifications(user: CurrentUser):
    """Honest status: the stored reminder preference exists, but no push delivery (service worker, subscriptions, a sender) has been built."""
    return {"delivery": "unavailable", "detail": "Reminder preferences are saved, but notifications are not delivered yet."}


@router.get("/occurrences", response_model=list[rol.OccurrenceOut])
def list_occurrences(db: DB, user: CurrentUser, start: date = Query(...), end: date = Query(...)):
    return rol.occurrences(db, user, start, end)


@router.post("", response_model=rol.EntryOut, status_code=201)
def create_entry(body: rol.EntryCreate, db: DB, user: CurrentUser):
    title = rol.resolve(db, user, body.kind, body.ref)
    start = body.start_date or utcnow().astimezone(ZoneInfo(body.timezone)).date()
    entry = RuleOfLifeEntry(user_id=user.id, kind=body.kind, ref=body.ref, title=title, local_time=body.local_time, timezone=body.timezone, recurrence=body.recurrence,
                            weekdays=body.weekdays, start_date=start, notify=body.notify, active=body.active)
    rol.ensure_unique(db, user, entry)
    db.add(entry)
    db.flush()
    return rol.out(db, user, entry)


@router.patch("/{entry_id}", response_model=rol.EntryOut)
def update_entry(entry_id: UUID, body: rol.EntryUpdate, db: DB, user: CurrentUser):
    entry = rol.owned(db, user, entry_id)
    changes = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    merged = rol.Schedule.model_validate({
        "local_time": entry.local_time, "timezone": entry.timezone, "recurrence": entry.recurrence, "weekdays": list(entry.weekdays or []), "start_date": entry.start_date,
        "notify": entry.notify, "active": entry.active, **changes})
    for field in ("local_time", "timezone", "recurrence", "weekdays", "start_date", "notify", "active"):
        setattr(entry, field, getattr(merged, field))
    rol.ensure_unique(db, user, entry)
    db.flush()
    return rol.out(db, user, entry)


@router.delete("/{entry_id}", status_code=204)
def delete_entry(entry_id: UUID, db: DB, user: CurrentUser):
    entry = rol.owned(db, user, entry_id)
    db.execute(delete(RuleOfLifeOccurrence).where(RuleOfLifeOccurrence.entry_id == entry.id))
    db.delete(entry)
    return Response(status_code=204)


@router.put("/{entry_id}/occurrences/{day}", response_model=rol.OccurrenceOut)
def mark_occurrence(entry_id: UUID, day: date, body: rol.MarkBody, db: DB, user: CurrentUser):
    """Idempotent: marking the same date again only changes its status."""
    entry = rol.owned(db, user, entry_id)
    if not rol.occurs_on(entry, day):
        raise HTTPException(422, "This prayer is not scheduled on that date")
    mark = db.scalar(select(RuleOfLifeOccurrence).where(RuleOfLifeOccurrence.entry_id == entry.id, RuleOfLifeOccurrence.occurrence_date == day))
    if mark is None:
        db.add(RuleOfLifeOccurrence(entry_id=entry.id, user_id=user.id, occurrence_date=day, status=body.status))
    else:
        mark.status, mark.marked_at = body.status, utcnow()
    db.flush()
    return next(o for o in rol.occurrences(db, user, day, day) if o.entry_id == entry.id)


@router.delete("/{entry_id}/occurrences/{day}", status_code=204)
def clear_occurrence(entry_id: UUID, day: date, db: DB, user: CurrentUser):
    entry = rol.owned(db, user, entry_id)
    db.execute(delete(RuleOfLifeOccurrence).where(RuleOfLifeOccurrence.entry_id == entry.id, RuleOfLifeOccurrence.occurrence_date == day))
    return Response(status_code=204)
