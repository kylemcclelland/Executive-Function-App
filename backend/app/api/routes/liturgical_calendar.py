# ruff: noqa: E501
from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request

from ...divine_office import calendar
from ...divine_office.engine import EngineConfig, EngineUnavailable
from ..dependencies import CurrentUser

# The traditional liturgical calendar (1960 Roman calendar). Signed-in users only, like the rest of the API.
router = APIRouter(prefix="/api/liturgical-calendar", tags=["liturgical-calendar"])


@router.get("/{day}", response_model=calendar.CalendarOut)
def read_calendar(day: date, request: Request, user: CurrentUser, edition: Literal["roman_1960"] = Query("roman_1960")):
    settings = request.app.state.settings
    config = EngineConfig(settings.divinum_officium_path, settings.divinum_officium_perl, settings.divinum_officium_perl5lib)
    try:
        return calendar.calendar(config, day)
    except EngineUnavailable as exc:
        raise HTTPException(503, f"The liturgical calendar is unavailable: {exc}") from exc
