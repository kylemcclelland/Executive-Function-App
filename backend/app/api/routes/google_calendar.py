"""Google Calendar integration: optional, per-user, read-only.

Identity always comes from the verified Clerk session (``current_user_id``). The OAuth callback is a
browser redirect from Google and cannot carry a Clerk token, so it is authenticated solely by a
single-use, expiring ``state`` that was issued to an authenticated user and bound to them.

Handlers here deliberately avoid the request-scoped session (which would hold a transaction open
across calls to Google) and use short transactions instead.
"""

import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, func, select, update

from ...core.config import Settings
from ...core.crypto import TokenCipher
from ...db import utcnow
from ...models import GoogleCalendarConnection, GoogleOAuthState
from ...schemas.calendar import (
    CalendarConnectOut,
    CalendarEventOut,
    CalendarEventsOut,
    CalendarStatusOut,
)
from ...services.google_calendar import (
    CALENDAR_SCOPE,
    AccessTokenRejected,
    GoogleCalendarClient,
    GoogleError,
    GoogleUnavailable,
    NeedsReauthorization,
    hash_state,
    new_pkce_pair,
    normalize_event,
)
from ..dependencies import current_user_id

logger = logging.getLogger("app.google_calendar")

PREFIX = "/api/integrations/google-calendar"
router = APIRouter(prefix=PREFIX)  # every route requires a Clerk session
callback_router = APIRouter(prefix=PREFIX)  # the callback is authenticated by `state` alone

STATE_LIFETIME = timedelta(minutes=10)
MAX_PENDING_STATES = 10
MAX_RANGE = timedelta(days=366)
DEFAULT_RANGE = timedelta(days=30)
SYNC_TOUCH_INTERVAL = timedelta(seconds=30)
MAX_PARAM = 2048


class GoogleCalendar:
    """What the app needs from Google, built once at startup when credentials are configured."""

    def __init__(self, settings: Settings, client: GoogleCalendarClient):
        self.client = client
        self.cipher = TokenCipher(settings.google_token_encryption_key.get_secret_value())
        self.frontend_url = settings.frontend_url.rstrip("/")


def google_of(request: Request) -> GoogleCalendar:
    google = request.app.state.google
    if google is None:
        raise HTTPException(503, "Google Calendar isn't set up on this server")
    return google


def live_connection(db, user_id) -> GoogleCalendarConnection | None:
    return db.scalar(select(GoogleCalendarConnection).where(
        GoogleCalendarConnection.user_id == user_id,
        GoogleCalendarConnection.connection_status != "disconnected",
    ))


# ------------------------------------------------------------------------ status

@router.get("/status", response_model=CalendarStatusOut)
def read_status(request: Request):
    user_id = current_user_id(request)
    configured = request.app.state.google is not None
    with request.app.state.session_factory() as db:
        connection = live_connection(db, user_id)
    if connection is None:
        return CalendarStatusOut(configured=configured, status="not_connected")
    return CalendarStatusOut(
        configured=configured, status=connection.connection_status,
        account_email=connection.google_account_email, connected_at=connection.connected_at,
        last_successful_sync_at=connection.last_successful_sync_at,
    )


# ------------------------------------------------------------------------ connect

@router.post("/connect", response_model=CalendarConnectOut)
def start_connection(request: Request):
    """Begin authorization. Nothing is sent to Google until the user chooses to connect."""
    user_id = current_user_id(request)
    google = google_of(request)
    state = secrets.token_urlsafe(32)
    verifier, challenge = new_pkce_pair()
    now = utcnow()
    with request.app.state.session_factory() as db, db.begin():
        db.execute(delete(GoogleOAuthState).where(
            GoogleOAuthState.user_id == user_id,
            (GoogleOAuthState.expires_at < now) | GoogleOAuthState.consumed_at.is_not(None),
        ))
        pending = db.scalar(select(func.count()).select_from(GoogleOAuthState).where(
            GoogleOAuthState.user_id == user_id,
        ))
        if pending >= MAX_PENDING_STATES:
            raise HTTPException(429, "Too many connection attempts. Please wait a few minutes.")
        db.add(GoogleOAuthState(
            user_id=user_id, state_hash=hash_state(state),
            encrypted_code_verifier=google.cipher.encrypt(verifier),
            expires_at=now + STATE_LIFETIME,
        ))
    return CalendarConnectOut(authorization_url=google.client.authorization_url(state, challenge))


def back_to_app(google: GoogleCalendar | None, request: Request, outcome: str) -> RedirectResponse:
    base = google.frontend_url if google else request.app.state.settings.frontend_url.rstrip("/")
    return RedirectResponse(
        f"{base}/calendar?{urlencode({'google': outcome})}", status_code=303,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


@callback_router.get("/callback", include_in_schema=False)
def finish_connection(
    request: Request, code: str | None = None, state: str | None = None, error: str | None = None,
):
    google = request.app.state.google
    if google is None or not state or len(state) > MAX_PARAM:
        return back_to_app(google, request, "invalid_state")
    session_factory = request.app.state.session_factory
    now = utcnow()
    # Consume the state atomically: valid once, within its lifetime, never again.
    with session_factory() as db, db.begin():
        consumed = db.execute(update(GoogleOAuthState).where(
            GoogleOAuthState.state_hash == hash_state(state),
            GoogleOAuthState.consumed_at.is_(None),
            GoogleOAuthState.expires_at > now,
        ).values(consumed_at=now)).rowcount
        row = db.scalar(select(GoogleOAuthState).where(
            GoogleOAuthState.state_hash == hash_state(state),
        )) if consumed == 1 else None
        if row is None:
            return back_to_app(google, request, "invalid_state")
        user_id, encrypted_verifier = row.user_id, row.encrypted_code_verifier
    if error or not code or len(code) > MAX_PARAM:
        return back_to_app(
            google, request, "access_denied" if error == "access_denied" else "failed",
        )
    verifier = google.cipher.decrypt(encrypted_verifier)
    if verifier is None:
        return back_to_app(google, request, "failed")
    try:
        tokens = google.client.exchange_code(code, verifier)
    except GoogleError as exc:
        logger.warning("Google authorization could not be completed (%s)", exc.code)
        return back_to_app(google, request, "failed")
    if CALENDAR_SCOPE not in tokens.scopes:
        # The user unticked calendar access on Google's consent screen.
        return back_to_app(google, request, "missing_scope")
    with session_factory() as db, db.begin():
        connection = db.scalar(select(GoogleCalendarConnection).where(
            GoogleCalendarConnection.user_id == user_id,
        ).order_by(GoogleCalendarConnection.connected_at.desc()))
        if tokens.refresh_token:
            encrypted = google.cipher.encrypt(tokens.refresh_token)
        elif (
            connection is not None and connection.connection_status != "disconnected"
            and connection.encrypted_refresh_token and tokens.account_id
            and connection.google_account_identifier == tokens.account_id
        ):
            # Google does not return a refresh token on every authorization. Keep the one we hold
            # for this same Google account; if it has been revoked, the next use says so.
            encrypted = connection.encrypted_refresh_token
        else:
            return back_to_app(google, request, "no_refresh_token")
        if connection is None:
            connection = GoogleCalendarConnection(user_id=user_id)
            db.add(connection)
        connection.google_account_identifier = tokens.account_id
        connection.google_account_email = tokens.account_email
        connection.encrypted_refresh_token = encrypted
        connection.granted_scopes = " ".join(sorted(tokens.scopes))
        connection.connection_status = "active"
        connection.connected_at = now
        connection.updated_at = now
        connection.last_successful_sync_at = None
        db.flush()
        google.client.forget(connection.id)
    return back_to_app(google, request, "connected")


# ------------------------------------------------------------------------ events

def utc(value: datetime | None, name: str) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise HTTPException(422, f"{name} must include a time zone, for example ending in Z")
    return value.astimezone(UTC)


def mark(request: Request, connection_id, **values) -> None:
    with request.app.state.session_factory() as db, db.begin():
        db.execute(update(GoogleCalendarConnection).where(
            GoogleCalendarConnection.id == connection_id,
        ).values(updated_at=utcnow(), **values))


@router.get("/events", response_model=CalendarEventsOut)
def list_events(
    request: Request,
    time_min: datetime | None = None,
    time_max: datetime | None = None,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
    page_token: Annotated[str | None, Query(max_length=MAX_PARAM)] = None,
):
    """Events from the signed-in user's own primary calendar, soonest first, recurring series
    expanded. Defaults to the next 30 days; pass ``next_page_token`` back as ``page_token``."""
    user_id = current_user_id(request)
    google = google_of(request)
    start = utc(time_min, "time_min") or utcnow()
    end = utc(time_max, "time_max") or start + DEFAULT_RANGE
    if end <= start:
        raise HTTPException(422, "time_max must be after time_min")
    if end - start > MAX_RANGE:
        raise HTTPException(422, "The date range can be at most 366 days")
    with request.app.state.session_factory() as db:
        connection = live_connection(db, user_id)
        if connection is not None:
            db.expunge(connection)
    if connection is None:
        raise HTTPException(409, "Google Calendar is not connected")
    if connection.connection_status == "needs_reauth":
        raise HTTPException(409, "Google Calendar needs to be reconnected")
    refresh_token = google.cipher.decrypt(connection.encrypted_refresh_token or "")
    if refresh_token is None:
        mark(request, connection.id, connection_status="needs_reauth")
        raise HTTPException(409, "Google Calendar needs to be reconnected")
    try:
        try:
            token = google.client.access_token(connection.id, refresh_token)
            page = google.client.list_events(token, start, end, page_size, page_token)
        except AccessTokenRejected:
            google.client.forget(connection.id)  # expired early or revoked: refresh once and retry
            token = google.client.access_token(connection.id, refresh_token)
            page = google.client.list_events(token, start, end, page_size, page_token)
    except NeedsReauthorization as exc:
        google.client.forget(connection.id)
        mark(request, connection.id, connection_status="needs_reauth")
        raise HTTPException(409, "Google Calendar needs to be reconnected") from exc
    except GoogleUnavailable as exc:
        raise HTTPException(
            503, "Google Calendar is temporarily unavailable. Please try again.",
            headers={"Retry-After": "30"},
        ) from exc
    except GoogleError as exc:
        logger.warning("Google Calendar request failed (%s)", exc.code)
        raise HTTPException(502, "Google Calendar could not be read right now.") from exc
    now = utcnow()
    last = connection.last_successful_sync_at
    if last is None or now - last > SYNC_TOUCH_INTERVAL:
        mark(request, connection.id, last_successful_sync_at=now)
    zone = page.get("timeZone") if isinstance(page.get("timeZone"), str) else None
    items = page.get("items") if isinstance(page.get("items"), list) else []
    events = [
        event for item in items if isinstance(item, dict)
        if (event := normalize_event(item, zone)) is not None
    ]
    next_token = page.get("nextPageToken")
    return CalendarEventsOut(
        events=[CalendarEventOut(**event) for event in events],
        next_page_token=next_token if isinstance(next_token, str) else None,
        time_min=start, time_max=end,
    )


# ------------------------------------------------------------------------ disconnect

@router.delete("/disconnect", status_code=204)
def disconnect(request: Request):
    """Forget the connection: revoke at Google (best effort), then erase the stored token."""
    user_id = current_user_id(request)
    google = request.app.state.google
    with request.app.state.session_factory() as db:
        connection = live_connection(db, user_id)
        if connection is not None:
            db.expunge(connection)
    if connection is not None:
        if google is not None and connection.encrypted_refresh_token:
            token = google.cipher.decrypt(connection.encrypted_refresh_token)
            if token is not None:
                google.client.revoke(token)
            google.client.forget(connection.id)
        mark(
            request, connection.id, connection_status="disconnected", encrypted_refresh_token=None,
            google_account_identifier=None, google_account_email=None, granted_scopes="",
            last_successful_sync_at=None,
        )
    with request.app.state.session_factory() as db, db.begin():
        db.execute(delete(GoogleOAuthState).where(GoogleOAuthState.user_id == user_id))
    return Response(status_code=204)
