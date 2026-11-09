"""Google OAuth 2.0 (authorization-code + PKCE) and the Calendar v3 events API.

This module never logs, returns or persists tokens. The only token Studium stores is the refresh
token, encrypted by the caller. Access tokens live briefly in this process's memory.
"""

import base64
import hashlib
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlencode
from uuid import UUID

import httpx
import jwt

from ..core.config import Settings

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
SCOPES = ("openid", "email", CALENDAR_SCOPE)
ISSUERS = {"https://accounts.google.com", "accounts.google.com"}
# Only what the UI shows: no descriptions, attendees or conference details are requested.
EVENT_FIELDS = (
    "nextPageToken,timeZone,"
    "items(id,status,summary,location,htmlLink,recurringEventId,start,end)"
)
EXPIRY_MARGIN = 60  # seconds


class GoogleError(Exception):
    """Base for failures talking to Google. ``code`` is a stable, non-sensitive label."""

    code = "google_error"


class NeedsReauthorization(GoogleError):
    """The refresh token is revoked, expired or otherwise no longer accepted (invalid_grant)."""

    code = "reauthorization_required"


class GoogleUnavailable(GoogleError):
    """A network failure, timeout, rate limit or 5xx; worth retrying later."""

    code = "unavailable"


class GoogleRejected(GoogleError):
    """Google refused the request for a reason retrying will not fix (API disabled, bad client)."""

    code = "rejected"


class AccessTokenRejected(GoogleError):
    """The Calendar API refused the access token (expired early or revoked)."""

    code = "access_token_rejected"


@dataclass
class Tokens:
    access_token: str
    expires_in: int
    refresh_token: str | None
    scopes: frozenset[str]
    account_id: str | None
    account_email: str | None


def new_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def hash_state(state: str) -> str:
    return hashlib.sha256(state.encode()).hexdigest()


class GoogleCalendarClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        assert settings.google_client_id and settings.google_client_secret
        self.client_id = settings.google_client_id
        self._client_secret = settings.google_client_secret.get_secret_value()
        self.redirect_uri = settings.google_redirect_uri
        self.http = httpx.Client(timeout=httpx.Timeout(10.0), transport=transport)
        self.clock = time.monotonic  # replaceable in tests
        self._access: dict[UUID, tuple[str, float]] = {}
        self._lock = threading.Lock()

    def close(self) -> None:
        self.http.close()

    # ---------------------------------------------------------------- authorization

    def authorization_url(self, state: str, code_challenge: str) -> str:
        return AUTH_URL + "?" + urlencode({
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            # Offline access yields a refresh token; consent is forced so Google actually returns
            # one on a reconnect. (Google may still omit it; callers must cope.)
            "access_type": "offline",
            "prompt": "consent",
        })

    def exchange_code(self, code: str, code_verifier: str) -> Tokens:
        body = self._token_request({
            "grant_type": "authorization_code", "code": code, "code_verifier": code_verifier,
            "redirect_uri": self.redirect_uri,
        })
        account_id, email = self._identity(body.get("id_token"))
        return Tokens(
            access_token=body["access_token"], expires_in=int(body.get("expires_in", 3600)),
            refresh_token=body.get("refresh_token"),
            scopes=frozenset(str(body.get("scope", "")).split()),
            account_id=account_id, account_email=email,
        )

    def _identity(self, id_token: str | None) -> tuple[str | None, str | None]:
        """Read who authorized. The token came straight from Google's token endpoint over TLS, so
        (per OpenID Connect Core 3.1.3.7) its signature need not be re-checked; audience, issuer
        and expiry are."""
        if not id_token:
            return None, None
        try:
            claims = jwt.decode(
                id_token, options={"verify_signature": False}, audience=self.client_id,
                algorithms=["RS256"],
            )
        except jwt.PyJWTError:
            return None, None
        if claims.get("iss") not in ISSUERS or not isinstance(claims.get("sub"), str):
            return None, None
        email = claims.get("email")
        return claims["sub"][:255], email[:320] if isinstance(email, str) else None

    # ---------------------------------------------------------------- access tokens

    def access_token(self, connection_id: UUID, refresh_token: str) -> str:
        with self._lock:
            cached = self._access.get(connection_id)
            if cached and cached[1] > self.clock():
                return cached[0]
        body = self._token_request({"grant_type": "refresh_token", "refresh_token": refresh_token})
        token = body["access_token"]
        lifetime = max(int(body.get("expires_in", 3600)) - EXPIRY_MARGIN, 0)
        with self._lock:
            self._access[connection_id] = (token, self.clock() + lifetime)
        return token

    def forget(self, connection_id: UUID) -> None:
        with self._lock:
            self._access.pop(connection_id, None)

    def _token_request(self, form: dict[str, str]) -> dict:
        form = {**form, "client_id": self.client_id, "client_secret": self._client_secret}
        try:
            response = self.http.post(TOKEN_URL, data=form)
        except httpx.HTTPError as exc:
            raise GoogleUnavailable("Could not reach Google") from exc
        if response.status_code == 200:
            try:
                body = response.json()
            except ValueError as exc:
                raise GoogleUnavailable("Unreadable response from Google") from exc
            if isinstance(body, dict) and body.get("access_token"):
                return body
            raise GoogleUnavailable("Unexpected response from Google")
        error = _error_name(response)
        if error == "invalid_grant":
            raise NeedsReauthorization("Google no longer accepts this authorization")
        if response.status_code == 429 or response.status_code >= 500:
            raise GoogleUnavailable("Google is temporarily unavailable")
        raise GoogleRejected("Google rejected the token request")

    def revoke(self, token: str) -> None:
        """Best effort: the local connection is removed whether or not Google confirms."""
        try:
            self.http.post(REVOKE_URL, data={"token": token})
        except httpx.HTTPError:
            pass

    # ---------------------------------------------------------------- events

    def list_events(
        self, access_token: str, time_min: datetime, time_max: datetime, page_size: int,
        page_token: str | None,
    ) -> dict:
        params = {
            "timeMin": rfc3339(time_min), "timeMax": rfc3339(time_max),
            # Expand recurring events into individual occurrences, in start order.
            "singleEvents": "true", "orderBy": "startTime",
            "maxResults": str(page_size), "fields": EVENT_FIELDS,
        }
        if page_token:
            params["pageToken"] = page_token
        try:
            response = self.http.get(
                EVENTS_URL, params=params, headers={"Authorization": f"Bearer {access_token}"},
            )
        except httpx.HTTPError as exc:
            raise GoogleUnavailable("Could not reach Google Calendar") from exc
        if response.status_code == 200:
            try:
                body = response.json()
            except ValueError as exc:
                raise GoogleUnavailable("Unreadable response from Google Calendar") from exc
            if isinstance(body, dict):
                return body
            raise GoogleUnavailable("Unexpected response from Google Calendar")
        if response.status_code == 401:
            raise AccessTokenRejected("Access token refused")
        if response.status_code == 429 or response.status_code >= 500:
            raise GoogleUnavailable("Google Calendar is temporarily unavailable")
        if response.status_code == 400:
            raise GoogleRejected("Google Calendar rejected the request (bad page token or range)")
        raise GoogleRejected("Google Calendar refused access")


def _error_name(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    error = body.get("error") if isinstance(body, dict) else None
    return error if isinstance(error, str) else None


def rfc3339(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# -------------------------------------------------------------------- normalization

def _instant(node: dict) -> datetime | None:
    raw = node.get("dateTime")
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else None


def _day(node: dict) -> date | None:
    raw = node.get("date")
    if not isinstance(raw, str):
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def normalize_event(raw: dict, calendar_time_zone: str | None) -> dict | None:
    """One Google event in Studium's shape, or None if it is cancelled or unusable.

    Timed events carry UTC instants plus the IANA zone they were scheduled in. All-day events carry
    calendar dates only, with an *inclusive* last day (Google's end date is exclusive). Recurring
    series arrive already expanded into occurrences (``singleEvents``).
    """
    if raw.get("status") == "cancelled" or not isinstance(raw.get("id"), str):
        return None
    start_node, end_node = raw.get("start") or {}, raw.get("end") or {}
    title = raw.get("summary")
    event = {
        "id": raw["id"],
        "title": title.strip() if isinstance(title, str) and title.strip() else "(No title)",
        "location": raw.get("location") if isinstance(raw.get("location"), str) else None,
        "html_link": raw.get("htmlLink") if isinstance(raw.get("htmlLink"), str) else None,
        "recurring": bool(raw.get("recurringEventId")),
        "start": None, "end": None, "start_date": None, "end_date": None, "time_zone": None,
    }
    first_day = _day(start_node)
    if first_day is not None:
        end_exclusive = _day(end_node) or first_day + timedelta(days=1)
        event.update(
            all_day=True, start_date=first_day,
            end_date=max(end_exclusive - timedelta(days=1), first_day),
        )
        return event
    start = _instant(start_node)
    if start is None:
        return None
    zone = start_node.get("timeZone")
    event.update(
        all_day=False, start=start, end=_instant(end_node) or start,
        time_zone=zone if isinstance(zone, str) else calendar_time_zone,
    )
    return event
