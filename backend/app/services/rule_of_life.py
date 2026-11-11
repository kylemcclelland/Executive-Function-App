# ruff: noqa: E501
"""Rule of Life: a user's scheduled prayers.

An entry only refers to an existing prayer (a whole Office hour or a library devotion such as the Rosary); no prayer text is copied. Entries that already refer to a saved
Office prayer are kept and still shown and scheduled (legacy), but no new one can be created.
Occurrences are calculated on demand from the entry's local time and IANA zone, so daylight saving time follows the zone's own rules. Notification *delivery* is not
implemented: ``notify`` is only the user's stored preference.
"""

from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from pydantic import BaseModel, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..divine_office import service
from ..models import Devotion, RuleOfLifeEntry, RuleOfLifeOccurrence, SavedOfficeUnit, User

MAX_WINDOW_DAYS = 62
HOURS = {h["slug"]: h for h in service.HOURS}
Kind = Literal["office_hour", "devotion"]       # what a NEW entry may reference; "saved_office" survives only on entries created before it was withdrawn
Recurrence = Literal["once", "daily", "weekly"]


def valid_zone(name: str) -> str:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
        raise ValueError("Unknown time zone") from exc
    return name


class Schedule(BaseModel):
    model_config = {"extra": "forbid"}
    local_time: time
    timezone: str
    recurrence: Recurrence
    weekdays: list[int] = []
    start_date: date | None = None
    notify: bool = False
    active: bool = True

    @field_validator("timezone")
    @classmethod
    def zone(cls, value: str) -> str:
        return valid_zone(value)

    @field_validator("local_time")
    @classmethod
    def whole_minutes(cls, value: time) -> time:
        return value.replace(second=0, microsecond=0, tzinfo=None)

    @model_validator(mode="after")
    def consistent(self):
        if self.recurrence == "weekly":
            if not self.weekdays or any(not 0 <= d <= 6 for d in self.weekdays):
                raise ValueError("Choose at least one weekday (0 = Monday … 6 = Sunday)")
            self.weekdays = sorted(set(self.weekdays))
        else:
            self.weekdays = []
        if self.recurrence == "once" and self.start_date is None:
            raise ValueError("A one-time prayer needs its date")
        return self


class EntryCreate(Schedule):
    kind: Kind
    ref: str


class EntryUpdate(BaseModel):
    model_config = {"extra": "forbid"}
    local_time: time | None = None
    timezone: str | None = None
    recurrence: Recurrence | None = None
    weekdays: list[int] | None = None
    start_date: date | None = None
    notify: bool | None = None
    active: bool | None = None


class EntryOut(BaseModel):
    id: UUID
    kind: str
    ref: str
    title: str
    local_time: str
    timezone: str
    recurrence: str
    weekdays: list[int]
    start_date: date
    notify: bool
    active: bool
    link: str
    available: bool


class OccurrenceOut(BaseModel):
    entry_id: UUID
    title: str
    kind: str
    date: date
    local_time: str
    start: datetime
    time_zone: str
    recurrence: str
    notify: bool
    link: str
    status: Literal["completed", "skipped"] | None = None


class MarkBody(BaseModel):
    model_config = {"extra": "forbid"}
    status: Literal["completed", "skipped"]


def fingerprint(kind: str, ref: str, local_time: time, recurrence: str, weekdays: list[int], start_date: date) -> str:
    when = start_date.isoformat() if recurrence == "once" else ""
    return f"{kind}|{ref}|{local_time:%H:%M}|{recurrence}|{','.join(map(str, sorted(weekdays)))}|{when}"


def link_for(entry: RuleOfLifeEntry, day: date | None = None) -> str:
    if entry.kind == "saved_office":
        return f"/divine-office/saved/{entry.ref}"
    if entry.kind == "office_hour":
        return f"/divine-office?date={(day or entry.start_date).isoformat()}&hour={entry.ref}"     # the Office of that occurrence's own date
    return f"/devotions/{entry.ref}"


def resolve(db: Session, user: User, kind: str, ref: str) -> str:
    """Validate the reference and return the prayer's name. ``saved_office`` is only ever resolved for legacy entries (ownership checked); creation never accepts it."""
    if kind == "saved_office":
        try:
            row = db.get(SavedOfficeUnit, UUID(ref))
        except ValueError:
            row = None
        if row is None or row.user_id != user.id:
            raise HTTPException(404, "Saved prayer not found")        # the same answer for "not yours" and "missing"
        return row.title_english or row.title_latin
    if kind == "office_hour":
        if ref not in HOURS or ref not in service.IMPLEMENTED:
            raise HTTPException(422, "Unknown or unavailable Office hour")
        return HOURS[ref]["name"]
    devotion = db.scalar(select(Devotion).where(Devotion.slug == ref))
    if devotion is None:
        raise HTTPException(404, "Prayer not found")
    return devotion.title


def is_available(db: Session, user: User, entry: RuleOfLifeEntry) -> bool:
    try:
        resolve(db, user, entry.kind, entry.ref)
        return True
    except HTTPException:
        return False


def out(db: Session, user: User, entry: RuleOfLifeEntry) -> EntryOut:
    return EntryOut(
        id=entry.id, kind=entry.kind, ref=entry.ref, title=entry.title, local_time=f"{entry.local_time:%H:%M}", timezone=entry.timezone, recurrence=entry.recurrence,
        weekdays=list(entry.weekdays or []), start_date=entry.start_date, notify=entry.notify, active=entry.active, link=link_for(entry), available=is_available(db, user, entry),
    )


def owned(db: Session, user: User, entry_id: UUID) -> RuleOfLifeEntry:
    entry = db.get(RuleOfLifeEntry, entry_id)
    if entry is None or entry.user_id != user.id:
        raise HTTPException(404, "Rule of Life entry not found")
    return entry


def ensure_unique(db: Session, user: User, entry: RuleOfLifeEntry) -> None:
    entry.fingerprint = fingerprint(entry.kind, entry.ref, entry.local_time, entry.recurrence, list(entry.weekdays or []), entry.start_date)
    with db.no_autoflush:                                       # the edited entry is not written until it is known to be free of clashes
        clash = db.scalar(select(RuleOfLifeEntry.id).where(RuleOfLifeEntry.user_id == user.id, RuleOfLifeEntry.fingerprint == entry.fingerprint, RuleOfLifeEntry.id != entry.id))
    if clash:
        raise HTTPException(409, "This prayer is already scheduled for that time")


def occurs_on(entry: RuleOfLifeEntry, day: date) -> bool:
    if day < entry.start_date:
        return False
    if entry.recurrence == "once":
        return day == entry.start_date
    return entry.recurrence == "daily" or day.weekday() in (entry.weekdays or [])


def instant(entry: RuleOfLifeEntry, day: date) -> datetime:
    """The UTC instant of the entry's local time on a local date; a time skipped by a clock change moves forward with the zone's own rules."""
    return datetime.combine(day, entry.local_time, tzinfo=ZoneInfo(entry.timezone)).astimezone(UTC)


def occurrences(db: Session, user: User, start: date, end: date) -> list[OccurrenceOut]:
    if end < start or (end - start).days > MAX_WINDOW_DAYS:
        raise HTTPException(422, f"Ask for at most {MAX_WINDOW_DAYS} days")
    entries = list(db.scalars(select(RuleOfLifeEntry).where(RuleOfLifeEntry.user_id == user.id, RuleOfLifeEntry.active.is_(True))))
    marks = {(m.entry_id, m.occurrence_date): m.status for m in db.scalars(select(RuleOfLifeOccurrence).where(
        RuleOfLifeOccurrence.user_id == user.id, RuleOfLifeOccurrence.occurrence_date >= start, RuleOfLifeOccurrence.occurrence_date <= end))}
    found = []
    for entry in entries:
        day = max(start, entry.start_date)
        while day <= end:
            if occurs_on(entry, day):
                found.append(OccurrenceOut(
                    entry_id=entry.id, title=entry.title, kind=entry.kind, date=day, local_time=f"{entry.local_time:%H:%M}", start=instant(entry, day), time_zone=entry.timezone,
                    recurrence=entry.recurrence, notify=entry.notify, link=link_for(entry, day), status=marks.get((entry.id, day))))
            day += timedelta(days=1)
    return sorted(found, key=lambda o: (o.start, o.title))
