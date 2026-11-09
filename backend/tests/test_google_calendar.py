import logging
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from alembic import command
from alembic.config import Config
from clerk_tokens import bearer
from cryptography.fernet import Fernet
from fake_google import CALENDAR_SCOPE, REDIRECT_URI, all_day, timed
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.core.config import LEGACY_USER_ID, Settings
from app.core.crypto import TokenCipher
from app.core.redaction import RedactOAuthParams, redact
from app.db import utcnow
from app.models import (
    GoogleCalendarConnection,
    GoogleOAuthState,
    Project,
    Task,
    User,
)

BASE = "/api/integrations/google-calendar"
ALICE, BOB = "user_alice", "user_bob"


def as_user(application, subject):
    return TestClient(application, headers=bearer(subject))


def browser(application):
    """The browser returning from Google: a top-level navigation that carries no Clerk token."""
    return TestClient(application, headers={}, follow_redirects=False)


def begin(application, fake, client, sub, **grant):
    """Press Connect, 'approve' at Google as ``sub``, and return the callback's query string."""
    response = client.post(f"{BASE}/connect")
    assert response.status_code == 200, response.text
    url = urlparse(response.json()["authorization_url"])
    query = {name: values[0] for name, values in parse_qs(url.query).items()}
    code = fake.issue_code(sub, query["code_challenge"], **grant)
    return query, f"?code={code}&state={query['state']}"


def connect(application, fake, client, sub, **grant):
    query, callback = begin(application, fake, client, sub, **grant)
    response = browser(application).get(f"{BASE}/callback{callback}")
    return response.headers["location"].split("google=")[-1]


@pytest.fixture
def google(application, fake_google):
    fake_google.add_account("g-alice", "alice@gmail.example", [
        timed("a1", "Alice standup", "2026-11-10T09:00:00-05:00", "2026-11-10T09:30:00-05:00"),
        timed("a2", "Alice dentist", "2026-11-11T15:00:00-05:00", "2026-11-11T16:00:00-05:00"),
    ])
    fake_google.add_account("g-bob", "bob@gmail.example", [
        timed("b1", "Bob review", "2026-11-10T14:00:00+01:00", "2026-11-10T15:00:00+01:00",
              tz="Europe/Paris"),
    ])
    return fake_google


# ------------------------------------------------------------------ optional by design

def test_studium_works_without_google_configured(application):
    application.state.google = None
    client = as_user(application, ALICE)
    status = client.get(f"{BASE}/status").json()
    assert status == {
        "configured": False, "status": "not_connected", "account_email": None,
        "connected_at": None, "last_successful_sync_at": None,
    }
    assert client.post(f"{BASE}/connect").status_code == 503
    assert client.get(f"{BASE}/events").status_code == 503
    assert client.delete(f"{BASE}/disconnect").status_code == 204
    assert client.post("/api/tasks", json={"title": "Still works"}).status_code == 201
    assert client.get("/api/today").status_code == 200


def test_signed_in_user_without_a_connection_can_use_studium(application, google):
    client = as_user(application, ALICE)
    status = client.get(f"{BASE}/status").json()
    assert status["configured"] is True and status["status"] == "not_connected"
    assert client.get(f"{BASE}/events").status_code == 409
    assert client.post("/api/tasks", json={"title": "Plan"}).status_code == 201
    assert google.requests == []  # Google is never contacted until the user chooses to connect


def test_simply_signing_in_never_starts_authorization(application, google):
    client = as_user(application, ALICE)
    client.get("/api/today")
    client.get(f"{BASE}/status")
    with application.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(GoogleOAuthState)) == 0


# ------------------------------------------------------------------ authentication

@pytest.mark.parametrize("method,path", [
    ("GET", "/status"), ("POST", "/connect"), ("GET", "/events"), ("DELETE", "/disconnect"),
])
def test_account_endpoints_require_clerk_authentication(application, google, method, path):
    anonymous = TestClient(application, headers={})
    assert anonymous.request(method, BASE + path).status_code == 401
    forged = TestClient(application, headers={"X-User-Id": str(LEGACY_USER_ID)})
    assert forged.request(method, BASE + path).status_code == 401


def test_a_user_id_from_the_client_is_never_accepted(application, google):
    alice, bob = as_user(application, ALICE), as_user(application, BOB)
    assert connect(application, google, alice, "g-alice") == "connected"
    with application.state.session_factory() as db:
        alice_id = db.scalar(select(User.id).where(User.clerk_user_id == ALICE))
    spoofed = bob.get(f"{BASE}/events", params={"user_id": str(alice_id)})
    assert spoofed.status_code == 409  # Bob has no connection, whatever he claims
    assert bob.get(f"{BASE}/status", headers={"X-User-Id": str(alice_id)}).json()[
        "status"] == "not_connected"


# ------------------------------------------------------------------ the OAuth flow

def test_authorization_request_is_correct(application, google):
    query, _ = begin(application, google, as_user(application, ALICE), "g-alice")
    assert query["response_type"] == "code"
    assert query["access_type"] == "offline"
    assert query["prompt"] == "consent"
    assert query["redirect_uri"] == REDIRECT_URI
    assert query["code_challenge_method"] == "S256"
    assert CALENDAR_SCOPE in query["scope"].split()
    assert "https://www.googleapis.com/auth/calendar " not in query["scope"] + " "  # read-only only
    assert len(query["state"]) >= 40
    assert "client_secret" not in query


def test_connect_is_post_only_and_get_does_nothing(application, google):
    assert as_user(application, ALICE).get(f"{BASE}/connect").status_code == 405


def test_successful_connection_returns_to_studium_and_persists(application, google):
    alice = as_user(application, ALICE)
    assert connect(application, google, alice, "g-alice") == "connected"
    status = alice.get(f"{BASE}/status").json()
    assert status["status"] == "active" and status["account_email"] == "alice@gmail.example"
    # A fresh login (new client / restarted server) still finds the connection.
    assert as_user(application, ALICE).get(f"{BASE}/status").json()["status"] == "active"
    from app.main import create_app
    restarted = create_app(application.state.settings)
    with TestClient(restarted, headers=bearer(ALICE)) as again:
        assert again.get(f"{BASE}/status").json()["status"] == "active"
    restarted.state.engine.dispose()


def test_callback_redirects_only_to_the_configured_frontend(application, google):
    alice = as_user(application, ALICE)
    for outcome in (connect(application, google, alice, "g-alice"),):
        assert outcome == "connected"
    response = browser(application).get(f"{BASE}/callback?state=nope")
    assert response.status_code == 303
    assert response.headers["location"] == "http://localhost:5173/calendar?google=invalid_state"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_refresh_token_is_encrypted_at_rest(application, google):
    alice = as_user(application, ALICE)
    connect(application, google, alice, "g-alice")
    token = google.accounts["g-alice"].refresh_token
    with application.state.session_factory() as db:
        stored = db.scalar(select(GoogleCalendarConnection.encrypted_refresh_token))
        raw = " ".join(
            str(value) for row in db.execute(text("SELECT * FROM google_calendar_connections"))
            for value in row
        )
    assert stored and stored != token and token not in raw
    assert application.state.google.cipher.decrypt(stored) == token
    # A different key cannot read it.
    assert TokenCipher(Fernet.generate_key().decode()).decrypt(stored) is None


def test_tokens_are_never_returned_to_the_browser(application, google):
    alice = as_user(application, ALICE)
    connect(application, google, alice, "g-alice")
    bodies = [
        alice.get(f"{BASE}/status").text, alice.get(f"{BASE}/events").text,
        alice.post(f"{BASE}/connect").text.split("?")[0],
    ]
    for secret in google.secrets_seen:
        assert all(secret not in body for body in bodies)


def test_state_is_single_use(application, google):
    alice = as_user(application, ALICE)
    _, callback = begin(application, google, alice, "g-alice")
    assert browser(application).get(f"{BASE}/callback{callback}").headers[
        "location"].endswith("google=connected")
    replay = browser(application).get(f"{BASE}/callback{callback}")
    assert replay.headers["location"].endswith("google=invalid_state")
    assert google.count("code-exchange") == 1  # the replay never reached Google


def test_state_expires(application, google):
    alice = as_user(application, ALICE)
    _, callback = begin(application, google, alice, "g-alice")
    with application.state.session_factory.begin() as db:
        db.execute(text("UPDATE google_oauth_states SET expires_at = :past"), {
            "past": utcnow() - timedelta(seconds=1),
        })
    response = browser(application).get(f"{BASE}/callback{callback}")
    assert response.headers["location"].endswith("google=invalid_state")
    assert alice.get(f"{BASE}/status").json()["status"] == "not_connected"
    assert google.count("code-exchange") == 0


def test_state_is_not_stored_in_plaintext_and_unknown_state_is_rejected(application, google):
    alice = as_user(application, ALICE)
    query, _ = begin(application, google, alice, "g-alice")
    with application.state.session_factory() as db:
        row = db.scalar(select(GoogleOAuthState))
        assert row.state_hash != query["state"]
        assert query["state"] not in row.encrypted_code_verifier
    tampered = query["state"][:-1] + ("B" if query["state"][-1] == "A" else "A")
    for bad in ("", "x" * 5000, "../../etc", tampered):
        response = browser(application).get(f"{BASE}/callback", params={"state": bad, "code": "c"})
        assert response.headers["location"].endswith("google=invalid_state"), bad[:20]
    assert browser(application).get(f"{BASE}/callback").headers["location"].endswith(
        "google=invalid_state")


def test_callback_binds_authorization_to_the_user_who_started_it(application, google):
    alice, bob = as_user(application, ALICE), as_user(application, BOB)
    _, callback = begin(application, google, alice, "g-alice")
    # Bob's browser (and Bob's Clerk token) completes the redirect; it still belongs to Alice.
    response = TestClient(application, headers=bearer(BOB), follow_redirects=False).get(
        f"{BASE}/callback{callback}")
    assert response.headers["location"].endswith("google=connected")
    assert alice.get(f"{BASE}/status").json()["status"] == "active"
    assert bob.get(f"{BASE}/status").json()["status"] == "not_connected"


def test_declining_consent_connects_nothing(application, google):
    alice = as_user(application, ALICE)
    query, _ = begin(application, google, alice, "g-alice")
    response = browser(application).get(
        f"{BASE}/callback", params={"error": "access_denied", "state": query["state"]})
    assert response.headers["location"].endswith("google=access_denied")
    assert alice.get(f"{BASE}/status").json()["status"] == "not_connected"
    # The state was spent, so the same link cannot be replayed.
    retry = browser(application).get(
        f"{BASE}/callback", params={"state": query["state"], "code": "x"})
    assert retry.headers["location"].endswith("google=invalid_state")


def test_calendar_scope_must_actually_be_granted(application, google):
    alice = as_user(application, ALICE)
    assert connect(application, google, alice, "g-alice", scopes=["openid", "email"]) == (
        "missing_scope")
    assert alice.get(f"{BASE}/status").json()["status"] == "not_connected"


def test_pkce_verifier_must_match(application, google):
    alice = as_user(application, ALICE)
    query, _ = begin(application, google, alice, "g-alice")
    wrong = google.issue_code("g-alice", "not-the-challenge")
    response = browser(application).get(f"{BASE}/callback?code={wrong}&state={query['state']}")
    assert response.headers["location"].endswith("google=failed")
    assert alice.get(f"{BASE}/status").json()["status"] == "not_connected"


def test_missing_refresh_token_is_not_assumed(application, google):
    alice = as_user(application, ALICE)
    # First authorization with no refresh token: nothing durable can be stored.
    assert connect(application, google, alice, "g-alice", with_refresh_token=False) == (
        "no_refresh_token")
    assert alice.get(f"{BASE}/status").json()["status"] == "not_connected"
    assert connect(application, google, alice, "g-alice") == "connected"
    # A later authorization of the same account without one keeps the stored token.
    assert connect(application, google, alice, "g-alice", with_refresh_token=False) == "connected"
    assert alice.get(f"{BASE}/events").status_code == 200
    # But a different Google account must not inherit it.
    assert connect(application, google, alice, "g-bob", with_refresh_token=False) == (
        "no_refresh_token")
    assert alice.get(f"{BASE}/status").json()["account_email"] == "alice@gmail.example"


def test_reconnecting_the_same_user_keeps_one_connection(application, google):
    alice = as_user(application, ALICE)
    connect(application, google, alice, "g-alice")
    connect(application, google, alice, "g-bob")  # switches Alice to a different Google account
    assert alice.get(f"{BASE}/status").json()["account_email"] == "bob@gmail.example"
    with application.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(GoogleCalendarConnection)) == 1


def test_one_live_connection_per_user_is_enforced_by_the_database(application, google):
    alice = as_user(application, ALICE)
    connect(application, google, alice, "g-alice")
    with application.state.session_factory() as db:
        user_id = db.scalar(select(User.id).where(User.clerk_user_id == ALICE))
    with pytest.raises(IntegrityError):
        with application.state.session_factory.begin() as db:
            db.add(GoogleCalendarConnection(user_id=user_id, connection_status="active"))
    with application.state.session_factory.begin() as db:  # disconnected history may coexist
        db.add(GoogleCalendarConnection(user_id=user_id, connection_status="disconnected"))


# ------------------------------------------------------------------ isolation

def test_two_users_two_google_accounts_see_only_their_own_events(application, google):
    alice, bob = as_user(application, ALICE), as_user(application, BOB)
    assert connect(application, google, alice, "g-alice") == "connected"
    assert connect(application, google, bob, "g-bob") == "connected"
    alice_events = alice.get(f"{BASE}/events").json()["events"]
    bob_events = bob.get(f"{BASE}/events").json()["events"]
    assert [event["title"] for event in alice_events] == ["Alice standup", "Alice dentist"]
    assert [event["title"] for event in bob_events] == ["Bob review"]
    assert alice.get(f"{BASE}/status").json()["account_email"] == "alice@gmail.example"
    assert bob.get(f"{BASE}/status").json()["account_email"] == "bob@gmail.example"


def test_disconnecting_one_user_leaves_the_other_connected(application, google):
    alice, bob = as_user(application, ALICE), as_user(application, BOB)
    connect(application, google, alice, "g-alice")
    connect(application, google, bob, "g-bob")
    alice_token = google.accounts["g-alice"].refresh_token
    assert alice.delete(f"{BASE}/disconnect").status_code == 204
    assert ("revoke", alice_token) in google.requests
    assert alice.get(f"{BASE}/status").json()["status"] == "not_connected"
    assert alice.get(f"{BASE}/events").status_code == 409
    assert bob.get(f"{BASE}/status").json()["status"] == "active"
    assert [e["title"] for e in bob.get(f"{BASE}/events").json()["events"]] == ["Bob review"]
    with application.state.session_factory() as db:
        row = db.scalar(select(GoogleCalendarConnection).join(
            User, User.id == GoogleCalendarConnection.user_id).where(User.clerk_user_id == ALICE))
        assert row.connection_status == "disconnected"
        assert row.encrypted_refresh_token is None and row.google_account_email is None


def test_disconnect_is_idempotent_and_reconnect_works(application, google):
    alice = as_user(application, ALICE)
    assert alice.delete(f"{BASE}/disconnect").status_code == 204
    connect(application, google, alice, "g-alice")
    assert alice.delete(f"{BASE}/disconnect").status_code == 204
    assert alice.delete(f"{BASE}/disconnect").status_code == 204
    assert connect(application, google, alice, "g-alice") == "connected"
    assert alice.get(f"{BASE}/status").json()["status"] == "active"
    assert len(alice.get(f"{BASE}/events").json()["events"]) == 2


def test_disconnect_survives_google_being_unreachable(application, google, monkeypatch):
    alice = as_user(application, ALICE)
    connect(application, google, alice, "g-alice")
    import httpx

    def down(request):
        raise httpx.ConnectError("offline")

    application.state.google.client.http = httpx.Client(transport=httpx.MockTransport(down))
    assert alice.delete(f"{BASE}/disconnect").status_code == 204
    assert alice.get(f"{BASE}/status").json()["status"] == "not_connected"


# ------------------------------------------------------------------ token refresh

def test_access_tokens_are_cached_then_refreshed_when_they_expire(application, google):
    alice = as_user(application, ALICE)
    connect(application, google, alice, "g-alice")
    alice.get(f"{BASE}/events")
    alice.get(f"{BASE}/events")
    assert google.count("refresh") == 1  # the second request reused the cached access token
    google.now += 3600  # past expiry
    assert alice.get(f"{BASE}/events").status_code == 200
    assert google.count("refresh") == 2


def test_an_access_token_rejected_early_is_refreshed_and_retried(application, google):
    alice = as_user(application, ALICE)
    connect(application, google, alice, "g-alice")
    alice.get(f"{BASE}/events")
    google.expire_access_tokens()  # Google now refuses what we cached, though our clock disagrees
    response = alice.get(f"{BASE}/events")
    assert response.status_code == 200 and len(response.json()["events"]) == 2
    assert google.count("refresh") == 2


def test_revoked_authorization_needs_reconnecting_then_recovers(application, google):
    alice = as_user(application, ALICE)
    connect(application, google, alice, "g-alice")
    google.accounts["g-alice"].revoked = True
    google.now += 3600
    response = alice.get(f"{BASE}/events")
    assert response.status_code == 409 and "reconnected" in response.json()["detail"]
    assert alice.get(f"{BASE}/status").json()["status"] == "needs_reauth"
    calls = google.count("refresh")
    assert alice.get(f"{BASE}/events").status_code == 409
    assert google.count("refresh") == calls  # no more pointless attempts with a dead token
    google.accounts["g-alice"].revoked = False
    google.accounts["g-alice"].refresh_token = "refresh-new"
    assert connect(application, google, alice, "g-alice") == "connected"
    assert alice.get(f"{BASE}/status").json()["status"] == "active"
    assert len(alice.get(f"{BASE}/events").json()["events"]) == 2


def test_undecryptable_token_is_treated_as_needing_reconnection(application, google):
    alice = as_user(application, ALICE)
    connect(application, google, alice, "g-alice")
    with application.state.session_factory.begin() as db:
        db.execute(text("UPDATE google_calendar_connections SET encrypted_refresh_token = 'junk'"))
    assert alice.get(f"{BASE}/events").status_code == 409
    assert alice.get(f"{BASE}/status").json()["status"] == "needs_reauth"


def test_google_outages_are_reported_without_disconnecting(application, google):
    alice = as_user(application, ALICE)
    connect(application, google, alice, "g-alice")
    google.fail_with = 503
    response = alice.get(f"{BASE}/events")
    assert response.status_code == 503 and response.headers["retry-after"]
    google.fail_with = 403
    assert alice.get(f"{BASE}/events").status_code == 502
    assert alice.get(f"{BASE}/status").json()["status"] == "active"
    assert alice.get(f"{BASE}/events").status_code == 200


def test_key_rotation_keeps_old_tokens_readable():
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    sealed = TokenCipher(old).encrypt("refresh-value")
    rotated = TokenCipher(f"{new},{old}")
    assert rotated.decrypt(sealed) == "refresh-value"
    assert TokenCipher(new).decrypt(rotated.encrypt("x")) == "x"
    assert TokenCipher(new).decrypt(sealed) is None


def test_a_malformed_encryption_key_is_refused_at_startup():
    with pytest.raises(ValidationError):
        Settings(app_env="test", google_token_encryption_key="not-a-fernet-key", _env_file=None)
    assert not Settings(app_env="test", google_client_id="id", _env_file=None).google_configured


# ------------------------------------------------------------------ events

def test_events_are_normalized(application, google):
    google.accounts["g-alice"].events = [
        timed("t", "Timed", "2026-11-10T09:00:00-05:00", "2026-11-10T10:30:00-05:00"),
        all_day("d", "Holiday", "2026-11-12", "2026-11-15"),
        all_day("one", "One day", "2026-11-20", "2026-11-21"),
        timed("r", "Weekly", "2026-11-17T09:00:00-05:00", "2026-11-17T09:30:00-05:00",
              recurringEventId="series"),
        timed("p", "Paris", "2026-11-18T18:00:00+01:00", "2026-11-18T19:00:00+01:00",
              tz="Europe/Paris", location="Café"),
        {"id": "gone", "status": "cancelled", "summary": "Cancelled"},
        {"id": "n", "start": {"dateTime": "2026-11-19T08:00:00Z"}, "end": {}},
        {"id": "bad", "summary": "No times"},
    ]
    alice = as_user(application, ALICE)
    connect(application, google, alice, "g-alice")
    events = {e["id"]: e for e in alice.get(f"{BASE}/events").json()["events"]}
    assert set(events) == {"t", "d", "one", "r", "p", "n"}
    assert events["t"]["start"] == "2026-11-10T14:00:00Z" and events["t"]["end"] == (
        "2026-11-10T15:30:00Z")
    assert events["t"]["time_zone"] == "America/New_York" and events["t"]["all_day"] is False
    assert events["t"]["start_date"] is None and events["t"]["recurring"] is False
    assert events["d"]["all_day"] is True and events["d"]["start"] is None
    assert events["d"]["start_date"] == "2026-11-12" and events["d"]["end_date"] == "2026-11-14"
    assert events["one"]["end_date"] == "2026-11-20"
    assert events["r"]["recurring"] is True
    assert events["p"]["start"] == "2026-11-18T17:00:00Z" and events["p"]["location"] == "Café"
    assert events["p"]["time_zone"] == "Europe/Paris"
    assert events["n"]["title"] == "(No title)" and events["n"]["end"] == events["n"]["start"]
    assert events["n"]["time_zone"] == "America/New_York"  # falls back to the calendar's zone


def test_range_defaults_and_validation(application, google):
    alice = as_user(application, ALICE)
    connect(application, google, alice, "g-alice")
    body = alice.get(f"{BASE}/events").json()
    query = google.event_queries[-1]
    assert query["singleEvents"] == "true" and query["orderBy"] == "startTime"
    assert query["maxResults"] == "50" and "pageToken" not in query
    assert "description" not in query["fields"] and "attendees" not in query["fields"]
    from datetime import datetime
    low = datetime.fromisoformat(body["time_min"])
    assert 29 <= (datetime.fromisoformat(body["time_max"]) - low).days <= 30
    ok = alice.get(f"{BASE}/events", params={
        "time_min": "2026-11-01T00:00:00Z", "time_max": "2026-12-01T00:00:00+01:00"})
    assert ok.status_code == 200
    assert google.event_queries[-1]["timeMin"] == "2026-11-01T00:00:00Z"
    assert google.event_queries[-1]["timeMax"] == "2026-11-30T23:00:00Z"
    bad = [
        {"time_min": "2026-11-01T00:00:00"},  # no zone
        {"time_min": "2026-11-02T00:00:00Z", "time_max": "2026-11-01T00:00:00Z"},
        {"time_min": "2026-01-01T00:00:00Z", "time_max": "2027-06-01T00:00:00Z"},
        {"page_size": 0}, {"page_size": 101}, {"page_token": "x" * 3000}, {"time_min": "soon"},
    ]
    for params in bad:
        assert alice.get(f"{BASE}/events", params=params).status_code == 422, params


def test_pagination(application, google):
    google.accounts["g-alice"].events = [
        timed(f"e{i}", f"Event {i}", f"2026-11-{10 + i}T09:00:00Z", f"2026-11-{10 + i}T10:00:00Z")
        for i in range(5)
    ]
    alice = as_user(application, ALICE)
    connect(application, google, alice, "g-alice")
    first = alice.get(f"{BASE}/events", params={"page_size": 2}).json()
    assert [e["id"] for e in first["events"]] == ["e0", "e1"] and first["next_page_token"]
    second = alice.get(f"{BASE}/events", params={
        "page_size": 2, "page_token": first["next_page_token"]}).json()
    assert [e["id"] for e in second["events"]] == ["e2", "e3"]
    last = alice.get(f"{BASE}/events", params={
        "page_size": 2, "page_token": second["next_page_token"]}).json()
    assert [e["id"] for e in last["events"]] == ["e4"] and last["next_page_token"] is None


def test_last_successful_sync_is_recorded(application, google):
    alice = as_user(application, ALICE)
    connect(application, google, alice, "g-alice")
    assert alice.get(f"{BASE}/status").json()["last_successful_sync_at"] is None
    alice.get(f"{BASE}/events")
    assert alice.get(f"{BASE}/status").json()["last_successful_sync_at"] is not None


# ------------------------------------------------------------------ logging

def test_no_token_or_code_reaches_the_logs(application, google, caplog):
    caplog.set_level(logging.DEBUG)
    alice = as_user(application, ALICE)
    query, callback = begin(application, google, alice, "g-alice")
    browser(application).get(f"{BASE}/callback{callback}")
    alice.get(f"{BASE}/events")
    google.accounts["g-alice"].revoked = True
    google.now += 3600
    alice.get(f"{BASE}/events")
    alice.delete(f"{BASE}/disconnect")
    google.secrets_seen.add(query["state"])
    log = caplog.text
    for secret in google.secrets_seen:
        assert secret not in log


def test_uvicorn_style_access_logs_are_redacted():
    line = '/api/integrations/google-calendar/callback?code=4/0Abc&state=s3cr3t&scope=x'
    assert "4/0Abc" not in redact(line) and "s3cr3t" not in redact(line)
    assert "scope=x" in redact(line)
    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:1", "GET", line, "1.1", 303), None,
    )
    RedactOAuthParams().filter(record)
    assert "s3cr3t" not in record.getMessage() and "REDACTED" in record.getMessage()


# ------------------------------------------------------------------ data safety

def test_migration_0009_is_additive_and_preserves_existing_data(application, google):
    with application.state.session_factory.begin() as db:
        db.add(User(id=LEGACY_USER_ID, timezone="UTC"))
        db.flush()
        project = Project(user_id=LEGACY_USER_ID, name="Kept")
        db.add(project)
        db.flush()
        db.add(Task(user_id=LEGACY_USER_ID, title="Kept task", project_id=project.id))
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with application.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0008")
        tables = {row[0] for row in connection.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table'"))} if (
            connection.dialect.name == "sqlite") else set()
        assert "google_calendar_connections" not in tables
        command.upgrade(config, "head")
    with application.state.session_factory() as db:
        assert db.scalar(select(Task.title)) == "Kept task"
        assert db.get(User, LEGACY_USER_ID).clerk_user_id is None
        assert db.scalar(select(func.count()).select_from(GoogleCalendarConnection)) == 0


def test_legacy_user_has_no_calendar_and_new_users_cannot_inherit_one(application, google):
    with application.state.session_factory.begin() as db:
        db.add(User(id=LEGACY_USER_ID, timezone="UTC"))
        db.flush()
        db.add(GoogleCalendarConnection(
            user_id=LEGACY_USER_ID, google_account_email="legacy@example.com",
            encrypted_refresh_token="x", connection_status="active",
        ))
    for subject in (ALICE, BOB):
        client = as_user(application, subject)
        assert client.get(f"{BASE}/status").json()["status"] == "not_connected"
        assert client.get(f"{BASE}/events").status_code == 409


def test_redaction_keeps_uvicorns_access_log_working():
    """The filter once emptied the record's args, so uvicorn's formatter failed on every line."""
    import io

    from uvicorn.logging import AccessFormatter

    from app.core.redaction import install_log_redaction

    install_log_redaction()
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    pattern = '%(client_addr)s - "%(request_line)s" %(status_code)s'
    handler.setFormatter(AccessFormatter(pattern, use_colors=False))
    logger = logging.getLogger("uvicorn.access")
    level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        logger.info(
            '%s - "%s %s HTTP/%s" %d', "10.0.0.1:5000", "GET",
            f"{BASE}/callback?code=4/0SECRETCODE&state=s3cr3t&scope=x", "1.1", 303,
        )
    finally:
        logger.removeHandler(handler)
        logger.setLevel(level)
    line = stream.getvalue()
    assert "Logging error" not in line and "303" in line
    assert "SECRETCODE" not in line and "s3cr3t" not in line and "scope=x" in line
