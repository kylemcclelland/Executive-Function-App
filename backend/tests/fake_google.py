"""A scripted stand-in for Google's OAuth and Calendar endpoints (via httpx.MockTransport)."""

import base64
import hashlib
import json
import secrets
from dataclasses import dataclass, field
from urllib.parse import parse_qs

import httpx
import jwt
from clerk_tokens import PRIVATE_KEY

CLIENT_ID = "test-client.apps.googleusercontent.com"
CLIENT_SECRET = "test-client-secret-value"
REDIRECT_URI = "http://localhost:5173/api/integrations/google-calendar/callback"
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"


@dataclass
class Account:
    email: str
    events: list[dict] = field(default_factory=list)
    refresh_token: str = field(default_factory=lambda: "refresh-" + secrets.token_hex(12))
    revoked: bool = False


@dataclass
class Grant:
    sub: str
    challenge: str
    scopes: list[str]
    with_refresh_token: bool


class FakeGoogle:
    def __init__(self):
        self.accounts: dict[str, Account] = {}
        self.grants: dict[str, Grant] = {}
        self.access_tokens: dict[str, tuple[str, float]] = {}  # token -> (sub, expires_at)
        self.now = 1000.0  # the app's access-token cache clock is pointed at this
        self.lifetime = 3600
        self.requests: list[tuple[str, str]] = []  # (kind, detail)
        self.event_queries: list[dict[str, str]] = []
        self.fail_with: int | None = None  # make the next Calendar call fail with this status
        self.secrets_seen: set[str] = set()  # everything that must never appear in logs

    def add_account(self, sub, email, events=None) -> Account:
        self.accounts[sub] = Account(email=email, events=events or [])
        self.secrets_seen.add(self.accounts[sub].refresh_token)
        return self.accounts[sub]

    def issue_code(self, sub, challenge, scopes=None, with_refresh_token=True) -> str:
        code = "code-" + secrets.token_hex(12)
        self.secrets_seen.add(code)
        self.grants[code] = Grant(
            sub, challenge, scopes or ["openid", "email", CALENDAR_SCOPE], with_refresh_token,
        )
        return code

    def count(self, kind: str) -> int:
        return sum(1 for entry in self.requests if entry[0] == kind)

    def expire_access_tokens(self) -> None:
        self.access_tokens = {token: (sub, 0.0) for token, (sub, _) in self.access_tokens.items()}

    # ---------------------------------------------------------------- transport

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com" and request.url.path == "/token":
            return self._token(parse_qs(request.content.decode()))
        if request.url.host == "oauth2.googleapis.com" and request.url.path == "/revoke":
            token = parse_qs(request.content.decode()).get("token", [""])[0]
            self.requests.append(("revoke", token))
            return httpx.Response(200, json={})
        if request.url.host == "www.googleapis.com" and request.url.path.endswith("/events"):
            return self._events(request)
        return httpx.Response(404, json={"error": "unexpected"})

    def _issue_access(self, sub) -> str:
        token = "access-" + secrets.token_hex(12)
        self.secrets_seen.add(token)
        self.access_tokens[token] = (sub, self.now + self.lifetime)
        return token

    def _token(self, form) -> httpx.Response:
        form = {name: values[0] for name, values in form.items()}
        if form.get("client_id") != CLIENT_ID or form.get("client_secret") != CLIENT_SECRET:
            return httpx.Response(401, json={"error": "invalid_client"})
        if form["grant_type"] == "authorization_code":
            self.requests.append(("code-exchange", ""))
            grant = self.grants.pop(form.get("code", ""), None)  # a code works once
            digest = hashlib.sha256(form.get("code_verifier", "").encode()).digest()
            challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
            if (
                grant is None or form.get("redirect_uri") != REDIRECT_URI
                or challenge != grant.challenge
            ):
                return httpx.Response(400, json={"error": "invalid_grant"})
            account = self.accounts[grant.sub]
            body = {
                "access_token": self._issue_access(grant.sub), "expires_in": self.lifetime,
                "scope": " ".join(grant.scopes), "token_type": "Bearer",
                "id_token": jwt.encode({
                    "iss": "https://accounts.google.com", "aud": CLIENT_ID, "sub": grant.sub,
                    "email": account.email, "exp": 4102444800,
                }, PRIVATE_KEY, algorithm="RS256"),
            }
            if grant.with_refresh_token:
                body["refresh_token"] = account.refresh_token
            return httpx.Response(200, json=body)
        if form["grant_type"] == "refresh_token":
            self.requests.append(("refresh", ""))
            owner = next((
                sub for sub, account in self.accounts.items()
                if account.refresh_token == form.get("refresh_token") and not account.revoked
            ), None)
            if owner is None:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(200, json={
                "access_token": self._issue_access(owner), "expires_in": self.lifetime,
            })
        return httpx.Response(400, json={"error": "unsupported_grant_type"})

    def _events(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(("events", ""))
        query = dict(request.url.params)
        self.event_queries.append(query)
        if self.fail_with is not None:
            status, self.fail_with = self.fail_with, None
            return httpx.Response(status, json={"error": {"message": "scripted failure"}})
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        entry = self.access_tokens.get(token)
        if entry is None or entry[1] <= self.now:
            return httpx.Response(401, json={"error": {"status": "UNAUTHENTICATED"}})
        events = self.accounts[entry[0]].events
        size, start = int(query.get("maxResults", 250)), int(query.get("pageToken", 0))
        body = {"timeZone": "America/New_York", "items": events[start:start + size]}
        if start + size < len(events):
            body["nextPageToken"] = str(start + size)
        return httpx.Response(
            200, content=json.dumps(body), headers={"content-type": "application/json"},
        )


def timed(id, title, start, end, tz="America/New_York", **extra):
    return {
        "id": id, "summary": title, "status": "confirmed",
        "start": {"dateTime": start, "timeZone": tz}, "end": {"dateTime": end, "timeZone": tz},
        **extra,
    }


def all_day(id, title, first, end_exclusive, **extra):
    return {
        "id": id, "summary": title, "status": "confirmed",
        "start": {"date": first}, "end": {"date": end_exclusive}, **extra,
    }
