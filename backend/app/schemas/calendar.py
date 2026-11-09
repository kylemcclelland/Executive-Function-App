from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class CalendarStatusOut(BaseModel):
    # False when the server has no Google credentials: the UI then offers nothing to connect.
    configured: bool
    status: Literal["not_connected", "active", "needs_reauth"]
    account_email: str | None = None
    connected_at: datetime | None = None
    last_successful_sync_at: datetime | None = None


class CalendarConnectOut(BaseModel):
    authorization_url: str


class CalendarEventOut(BaseModel):
    id: str
    title: str
    all_day: bool
    # Timed events: UTC instants plus the IANA zone they were scheduled in.
    start: datetime | None = None
    end: datetime | None = None
    time_zone: str | None = None
    # All-day events: calendar dates; end_date is the inclusive last day.
    start_date: date | None = None
    end_date: date | None = None
    location: str | None = None
    html_link: str | None = None
    recurring: bool = False


class CalendarEventsOut(BaseModel):
    events: list[CalendarEventOut]
    next_page_token: str | None = None
    time_min: datetime
    time_max: datetime
