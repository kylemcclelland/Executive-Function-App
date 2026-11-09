import re
import time
from pathlib import Path
from uuid import uuid4

import jwt
import pytest
from alembic import command
from alembic.config import Config
from clerk_tokens import (
    AUTHORIZED_ORIGIN,
    OTHER_PRIVATE_KEY,
    PUBLIC_KEY,
    bearer,
    make_token,
)
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select

from app.core.config import LEGACY_USER_ID, Settings
from app.main import create_app
from app.models import Book, InboxItem, Note, Project, Task, User

ALICE = "user_alice"
BOB = "user_bob"


def as_user(application, subject):
    return TestClient(application, headers=bearer(subject))


def anonymous(application):
    return TestClient(application, headers={}, raise_server_exceptions=False)


def protected_operations(application):
    """Every (method, path) in the OpenAPI schema except the public health check."""
    return [
        (method.upper(), path)
        for path, operations in application.openapi()["paths"].items() if path != "/health"
        for method in operations
    ]


def is_empty(body):
    return not (body.get("items") if isinstance(body, dict) else body)


# ------------------------------------------------------------ enforcement

def test_every_endpoint_rejects_unauthenticated_requests(application):
    operations = protected_operations(application)
    assert len(operations) > 50  # guards against the loop silently covering nothing
    client = anonymous(application)
    for method, route in operations:
        path = re.sub(r"\{[^}]+\}", str(uuid4()), route)
        response = client.request(method, path, json={})
        assert response.status_code == 401, (method, route, response.status_code)
        assert response.headers["www-authenticate"] == "Bearer"
        assert response.json() == {"detail": "Authentication required"}


def test_health_check_stays_public(application):
    assert anonymous(application).get("/health").json() == {"status": "ok"}


def test_unauthenticated_requests_create_no_user(application):
    anonymous(application).get("/api/tasks")
    with application.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 0


@pytest.mark.parametrize("headers", [
    {"Authorization": "Bearer"},
    {"Authorization": "Bearer "},
    {"Authorization": "Basic dXNlcjpwYXNz"},
    {"Authorization": "Bearer not-a-jwt"},
    {"Authorization": "Bearer ak_live_pretend_api_key"},
    {"Authorization": "Bearer m2m_pretend_machine_token"},
    {"Authorization": "Bearer oat_pretend_oauth_token"},
])
def test_malformed_and_non_session_credentials_are_rejected(application, headers):
    assert TestClient(application, headers=headers).get("/api/tasks").status_code == 401


@pytest.mark.parametrize("claims", [
    {"exp": int(time.time()) - 3600, "iat": int(time.time()) - 7200},
    {"nbf": int(time.time()) + 3600},
    {"azp": "https://evil.example"},
    {"azp": None},
    {"sub": None},
    {"sub": ""},
    {"sub": "org_123"},
    {"sub": "mt_machine"},
    {"sub": "user_" + "x" * 300},
    {"sts": "pending"},
])
def test_invalid_claims_are_rejected(application, claims):
    assert TestClient(application, headers=bearer(**claims)).get("/api/tasks").status_code == 401


def test_token_signed_by_another_key_is_rejected(application):
    headers = {"Authorization": f"Bearer {make_token(key=OTHER_PRIVATE_KEY)}"}
    assert TestClient(application, headers=headers).get("/api/tasks").status_code == 401


def test_unsigned_token_is_rejected(application):
    token = jwt.encode({"sub": ALICE, "azp": AUTHORIZED_ORIGIN}, key=None, algorithm="none")
    headers = {"Authorization": f"Bearer {token}"}
    assert TestClient(application, headers=headers).get("/api/tasks").status_code == 401


def test_session_cookie_is_never_accepted(application):
    cookie = {"Cookie": f"__session={make_token()}"}
    assert TestClient(application, headers=cookie).get("/api/tasks").status_code == 401


def test_client_supplied_identity_is_ignored(client, application):
    mine = client.post("/api/tasks", json={"title": "Mine"}).json()
    client.get("/api/user")
    with application.state.session_factory() as db:
        victim_id = db.scalar(select(User.id).where(User.clerk_user_id == "user_test_default"))
    spoofed = TestClient(application, headers={
        **bearer(BOB), "X-User-Id": str(victim_id), "X-Clerk-User-Id": "user_test_default",
    })
    assert spoofed.get("/api/tasks", params={"user_id": str(victim_id)}).json() == []
    assert spoofed.get(f"/api/tasks/{mine['id']}").status_code == 404
    response = spoofed.post("/api/tasks", json={"title": "x", "user_id": str(victim_id)})
    assert response.status_code == 422
    assert [task["title"] for task in client.get("/api/tasks").json()] == ["Mine"]


def test_authentication_unavailable_fails_closed(application):
    application.state.authenticator = None
    assert TestClient(application).get("/api/tasks").status_code == 503
    assert TestClient(application).get("/health").status_code == 200


def test_clerk_outage_is_unavailable_not_signed_out(application, monkeypatch):
    import app.core.auth as auth

    def broken(*args, **kwargs):
        raise OSError("network down")

    monkeypatch.setattr(auth, "authenticate_request", broken)
    client = TestClient(application, raise_server_exceptions=False)
    assert client.get("/api/tasks").status_code == 503


# ------------------------------------------------------------ identity

def test_identity_comes_only_from_verified_subject(application):
    alice = as_user(application, ALICE)
    assert alice.get("/api/user").status_code == 200
    assert alice.get("/api/user").status_code == 200  # repeat visits reuse the same account
    as_user(application, BOB).get("/api/user")
    with application.state.session_factory() as db:
        users = db.scalars(select(User).order_by(User.clerk_user_id)).all()
    assert [user.clerk_user_id for user in users] == [ALICE, BOB]
    assert len({user.id for user in users}) == 2


def test_users_cannot_see_or_touch_each_others_data(application):
    alice, bob = as_user(application, ALICE), as_user(application, BOB)
    task = alice.post("/api/tasks", json={"title": "Alice task"}).json()
    inbox = alice.post("/api/inbox", json={"content": "Alice thought"}).json()
    project = alice.post("/api/projects", json={"name": "Alice project"}).json()
    book = alice.post("/api/books", json={"title": "Alice book"}).json()
    note = alice.post("/api/notes", json={"title": "Alice note"}).json()

    for listing in ("/api/tasks", "/api/inbox", "/api/projects", "/api/books", "/api/notes"):
        assert is_empty(bob.get(listing).json()), listing
    for path in (
        f"/api/tasks/{task['id']}", f"/api/projects/{project['id']}",
        f"/api/books/{book['id']}", f"/api/notes/{note['id']}",
    ):
        assert bob.get(path).status_code == 404, path
    assert bob.patch(f"/api/inbox/{inbox['id']}", json={"status": "archived"}).status_code == 404
    assert bob.patch(f"/api/tasks/{task['id']}", json={"title": "Hijack"}).status_code == 404
    assert bob.delete(f"/api/projects/{project['id']}").status_code == 404
    assert bob.put("/api/today/priorities", json={"task_ids": [task["id"]]}).status_code == 404
    assert alice.get("/api/tasks").json()[0]["title"] == "Alice task"
    assert alice.get(f"/api/projects/{project['id']}").status_code == 200


def test_cover_enrichment_is_authenticated(application):
    assert anonymous(application).post("/api/books/covers/enrich", json={}).status_code == 401
    assert as_user(application, BOB).post("/api/books/covers/enrich", json={}).status_code == 200


# ------------------------------------------------------------ legacy data

def seed_legacy(application):
    with application.state.session_factory.begin() as db:
        db.add(User(id=LEGACY_USER_ID, timezone="UTC"))
        db.flush()
        project = Project(user_id=LEGACY_USER_ID, name="Legacy project")
        db.add(project)
        db.flush()
        task = Task(user_id=LEGACY_USER_ID, title="Legacy task", project_id=project.id)
        book = Book(user_id=LEGACY_USER_ID, title="Legacy book", authors=[])
        db.add_all([
            task, book, InboxItem(user_id=LEGACY_USER_ID, content="Legacy thought"),
            Note(user_id=LEGACY_USER_ID, title="Legacy note", content="x"),
        ])
        db.flush()
        return {"task": str(task.id), "project": str(project.id), "book": str(book.id)}


def test_new_accounts_never_see_pre_authentication_data(application):
    ids = seed_legacy(application)
    for subject in (ALICE, BOB, "user_test_default"):
        client = as_user(application, subject)
        for listing in ("/api/tasks", "/api/inbox", "/api/projects", "/api/books", "/api/notes"):
            assert is_empty(client.get(listing).json()), (subject, listing)
        assert client.get(f"/api/tasks/{ids['task']}").status_code == 404
        assert client.get(f"/api/projects/{ids['project']}").status_code == 404
        assert client.get(f"/api/books/{ids['book']}").status_code == 404
    with application.state.session_factory() as db:
        assert db.get(User, LEGACY_USER_ID).clerk_user_id is None
        assert db.scalar(
            select(func.count()).select_from(Task).where(Task.user_id == LEGACY_USER_ID)
        ) == 1


# ------------------------------------------------------------ configuration

def test_production_starts_only_with_clerk_configured():
    with pytest.raises(RuntimeError, match="Clerk"):
        create_app(Settings(app_env="production", _env_file=None))
    app = create_app(Settings(
        app_env="production", database_url="sqlite://", clerk_jwt_key=PUBLIC_KEY, _env_file=None,
    ))
    assert app.state.authenticator is not None
    app.state.engine.dispose()


def test_blank_clerk_settings_mean_unconfigured(monkeypatch):
    monkeypatch.setenv("CLERK_SECRET_KEY", "")
    monkeypatch.setenv("CLERK_JWT_KEY", "  ")
    assert not Settings(app_env="test", _env_file=None).clerk_configured
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_value")
    settings = Settings(app_env="test", _env_file=None)
    assert settings.clerk_configured
    assert "sk_test_value" not in repr(settings)
    assert isinstance(settings.clerk_secret_key, SecretStr)


def test_authorized_parties_default_to_cors_origins(monkeypatch):
    monkeypatch.delenv("CLERK_AUTHORIZED_PARTIES", raising=False)
    settings = Settings(app_env="test", cors_origins=["http://localhost:5173"], _env_file=None)
    assert settings.authorized_parties == ["http://localhost:5173"]
    monkeypatch.setenv("CLERK_AUTHORIZED_PARTIES", "https://a.example, https://b.example")
    assert Settings(app_env="test", _env_file=None).authorized_parties == [
        "https://a.example", "https://b.example",
    ]


def test_cors_permits_authorization_header(application):
    response = TestClient(application, headers={}).options("/api/tasks", headers={
        "Origin": AUTHORIZED_ORIGIN, "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "authorization",
    })
    assert response.status_code == 200
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


# ------------------------------------------------------------ migration

def test_clerk_migration_is_additive_and_leaves_legacy_data_unlinked(application):
    ids = seed_legacy(application)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with application.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0007")
        command.upgrade(config, "head")
    with application.state.session_factory() as db:
        legacy = db.get(User, LEGACY_USER_ID)
        assert legacy is not None and legacy.clerk_user_id is None
        assert str(db.scalar(select(Task.id))) == ids["task"]
        assert db.scalar(
            select(func.count()).select_from(Task).where(Task.user_id == LEGACY_USER_ID)
        ) == 1
