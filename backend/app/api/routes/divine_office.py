# ruff: noqa: E501
from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response

from ...divine_office import saved, service
from ...divine_office.engine import EngineConfig, EngineUnavailable
from ..dependencies import DB, CurrentUser

# The Divine Office (Roman Breviary, 1960). Signed-in users only, like the rest of the API.
router = APIRouter(prefix="/api/divine-office", tags=["divine-office"])


def engine_config(request: Request) -> EngineConfig:
    settings = request.app.state.settings
    return EngineConfig(settings.divinum_officium_path, settings.divinum_officium_perl, settings.divinum_officium_perl5lib)


@router.get("/hours", response_model=list[service.HourInfo])
def hours(user: CurrentUser):
    return service.hours_listing()


# ---- Saved prayers (declared before the dated routes so "saved" is never read as a date) -------------------------
@router.get("/saved", response_model=list[saved.SavedBrief])
def list_saved(db: DB, user: CurrentUser):
    return [saved._brief(row) for row in saved.listing(db, user)]


@router.post("/saved", response_model=saved.SaveResult)
def save_unit(body: saved.SaveRequest, db: DB, user: CurrentUser, request: Request, response: Response):
    row, created = saved.save(db, user, engine_config(request), body)
    response.status_code = 201 if created else 200
    return {"saved": True, "item": saved._brief(row)}


@router.get("/saved/{saved_id}", response_model=saved.SavedDetail)
def read_saved(saved_id: UUID, db: DB, user: CurrentUser):
    return saved._detail(saved.owned(db, user, saved_id))


@router.delete("/saved/{saved_id}")
def delete_saved(saved_id: UUID, db: DB, user: CurrentUser):
    db.delete(saved.owned(db, user, saved_id))
    return {"saved": False}


@router.get("/{day}/{hour}", response_model=service.OfficeOut)
def read_office(
    day: date, hour: str, request: Request, user: CurrentUser,
    language: Literal["both", "latin", "english"] = Query("both"),
):
    if hour not in {h["slug"] for h in service.HOURS}:
        raise HTTPException(404, "Unknown hour")
    if hour not in service.IMPLEMENTED:
        raise HTTPException(501, f"{hour.capitalize()} is not available.")
    try:
        result = service.office(engine_config(request), day, hour)
    except EngineUnavailable as exc:
        raise HTTPException(503, f"The Divine Office is unavailable: {exc}") from exc
    if language == "both":
        return result
    drop = "english" if language == "latin" else "latin"
    narrowed = result.model_copy(deep=True)
    for section in narrowed.sections:
        setattr(section, f"heading_{drop}", None)
        setattr(section, f"note_{drop}", None)
        for row in section.rows:
            setattr(row, drop, [])
            for mark in row.marks:
                setattr(mark, drop, None if drop == "english" else "")
            for unit in row.units:
                if drop == "english":
                    unit.title_english = None
                else:
                    unit.title_latin = ""
    return narrowed
