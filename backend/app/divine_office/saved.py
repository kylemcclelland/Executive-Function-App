# ruff: noqa: E501
"""Saved Divine Office prayers: the server finds the unit in the engine's own Office, snapshots it, and keeps it for one user."""

import re
from datetime import date
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..models import SavedOfficeUnit, User
from . import service
from .engine import EngineConfig, EngineUnavailable
from .units import ID_PATTERN

HOUR_SLUGS = {h["slug"] for h in service.HOURS}


class SaveRequest(BaseModel):
    """Only a reference: which Office (date, hour) and which unit. No prayer text is ever accepted from the client."""

    model_config = {"extra": "forbid"}
    date: date
    hour: str
    unit_id: str

    @field_validator("hour")
    @classmethod
    def known_hour(cls, value: str) -> str:
        if value not in HOUR_SLUGS:
            raise ValueError("Unknown hour")
        return value

    @field_validator("unit_id")
    @classmethod
    def well_formed(cls, value: str) -> str:
        if not ID_PATTERN.match(value):
            raise ValueError("Not a valid prayer identifier")
        return value


class SavedBrief(BaseModel):
    id: UUID
    unit_key: str
    kind: str
    title_latin: str
    title_english: str | None
    date_specific: bool
    source_hour: str
    source_hour_name: str
    source_date: date


class SavedDetail(SavedBrief):
    latin: list[service.LineOut]
    english: list[service.LineOut]
    source: service.SourceOut


class SaveResult(BaseModel):
    saved: bool
    item: SavedBrief


def _brief(row: SavedOfficeUnit) -> dict:
    names = {h["slug"]: h["name"] for h in service.HOURS}
    return {
        "id": row.id, "unit_key": row.unit_key, "kind": row.kind, "title_latin": row.title_latin, "title_english": row.title_english,
        "date_specific": row.date_specific, "source_hour": row.source_hour, "source_hour_name": names.get(row.source_hour, row.source_hour),
        "source_date": row.source_date,
    }


def _detail(row: SavedOfficeUnit) -> dict:
    return {**_brief(row), "latin": row.content["latin"], "english": row.content["english"], "source": row.source}


def find_unit(config: EngineConfig, request: SaveRequest):
    """The unit as the engine's Office for that date and hour offers it, with the row that holds it; 404 if it is not offered."""
    try:
        office = service.office(config, request.date, request.hour)
    except EngineUnavailable as exc:
        raise HTTPException(503, f"The Divine Office is unavailable: {exc}") from exc
    for section in office.sections:
        for row in section.rows:
            for unit in row.units:
                if unit.id == request.unit_id:
                    return office, row, unit
    raise HTTPException(404, "That selection is not a saveable prayer of this Office")


def save(db: Session, user: User, config: EngineConfig, request: SaveRequest) -> tuple[SavedOfficeUnit, bool]:
    office, row, unit = find_unit(config, request)
    existing = db.scalar(select(SavedOfficeUnit).where(SavedOfficeUnit.user_id == user.id, SavedOfficeUnit.unit_key == unit.id))
    if existing is not None:
        return existing, False
    snapshot = {
        "latin": [line.model_dump() for line in row.latin[unit.start:unit.end]],
        "english": [line.model_dump() for line in row.english[unit.start:unit.end]],
    }
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    db.execute(
        insert(SavedOfficeUnit).values(
            user_id=user.id, unit_key=unit.id, kind=unit.kind, title_latin=unit.title_latin, title_english=unit.title_english,
            date_specific=unit.date_specific, source_hour=office.hour, source_date=office.date, content=snapshot,
            source=office.source.model_dump(),
        ).on_conflict_do_nothing(index_elements=["user_id", "unit_key"]),
    )
    db.flush()
    created = db.scalar(select(SavedOfficeUnit).where(SavedOfficeUnit.user_id == user.id, SavedOfficeUnit.unit_key == unit.id))
    return created, True


def owned(db: Session, user: User, saved_id: UUID) -> SavedOfficeUnit:
    row = db.get(SavedOfficeUnit, saved_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "Saved prayer not found")       # the same answer for "not yours" and "missing"
    return row


def listing(db: Session, user: User) -> list[SavedOfficeUnit]:
    return list(db.scalars(select(SavedOfficeUnit).where(SavedOfficeUnit.user_id == user.id).order_by(SavedOfficeUnit.created_at.desc())))


UUID_PATTERN = re.compile(r"^[0-9a-fA-F-]{32,36}$")
