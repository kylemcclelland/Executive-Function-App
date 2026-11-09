import pytest
from clerk_tokens import AUTHORIZED_ORIGIN, PUBLIC_KEY, bearer
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

ORIGIN = "https://optima-pars.example.com"
HOST = "database.invalid"  # reserved TLD: can never resolve, so no test reaches a real server
NEON = f"postgresql+psycopg://owner:pw@{HOST}/optima?sslmode=require"
BASE = "/api/integrations/google-calendar"


def production(**overrides) -> Settings:
    values = dict(
        app_env="production", database_url=NEON, clerk_secret_key="sk_live_example",
        clerk_authorized_parties=[ORIGIN], cors_origins=[], frontend_url=ORIGIN,
        _env_file=None,
    )
    values.update(overrides)
    return Settings(**values)


def google(**overrides):
    values = dict(
        google_client_id="id.apps.googleusercontent.com", google_client_secret="secret",
        google_token_encryption_key=Fernet.generate_key().decode(),
        google_redirect_uri=f"{ORIGIN}{BASE}/callback",
    )
    values.update(overrides)
    return values


def test_a_complete_production_configuration_starts_and_hides_the_docs():
    app = create_app(production())
    try:
        client = TestClient(app, raise_server_exceptions=False)
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert client.get(path).status_code == 404, path
        assert app.state.google is None
    finally:
        app.state.engine.dispose()


def test_google_calendar_may_be_enabled_in_production():
    app = create_app(production(**google()))
    assert app.state.google is not None
    app.state.engine.dispose()


def test_the_development_docs_are_still_available_outside_production(application):
    assert TestClient(application, headers={}).get("/docs").status_code == 200


@pytest.mark.parametrize("overrides, fragment", [
    (dict(database_url="sqlite:///data/app.db"), "must be PostgreSQL"),
    (dict(database_url=NEON.replace("?sslmode=require", "")), "sslmode=require"),
    (dict(database_url=NEON.replace("?sslmode=require", "?sslmode=disable")), "sslmode=require"),
    (dict(clerk_secret_key=None), "CLERK_SECRET_KEY"),
    (dict(clerk_authorized_parties=None), "CLERK_AUTHORIZED_PARTIES"),
    (dict(clerk_authorized_parties=["http://optima-pars.example.com"]), "https"),
    (dict(clerk_authorized_parties=["https://localhost:5173"]), "not local"),
    (dict(clerk_authorized_parties=["https://*.vercel.app"]), "wildcard"),
    (dict(cors_origins=["http://localhost:5173"]), "https"),
    (dict(frontend_url="http://localhost:5173"), "https"),
    (dict(google_client_id="only-the-id"), "must be set together"),
    (google(google_redirect_uri="http://optima-pars.example.com/cb"), "https"),
])
def test_unsafe_production_settings_refuse_to_start(overrides, fragment):
    with pytest.raises(RuntimeError, match="Production configuration refused") as raised:
        create_app(production(**overrides))
    assert fragment in str(raised.value)


def test_every_problem_is_reported_at_once_and_no_secret_is_printed():
    settings = production(
        database_url="sqlite:///x.db", clerk_secret_key="sk_live_SUPERSECRET",
        clerk_authorized_parties=["http://localhost:5173"],
    )
    with pytest.raises(RuntimeError) as raised:
        create_app(settings)
    message = str(raised.value)
    assert message.count("\n  - ") >= 2
    assert "SUPERSECRET" not in message and "owner:pw" not in message


def test_a_private_database_host_does_not_need_ssl():
    internal = NEON.replace(HOST, "pg.railway.internal")
    plain = internal.replace("?sslmode=require", "")
    assert production(database_url=plain).production_problems() == []


def test_development_keys_are_allowed_for_private_staging_but_warn(caplog):
    with caplog.at_level("WARNING", logger="app.config"):
        app = create_app(production(clerk_secret_key="sk_test_staging"))
    app.state.engine.dispose()
    assert "development keys" in caplog.text and "sk_test_staging" not in caplog.text


def test_the_api_sets_defensive_headers_and_never_caches(application):
    client = TestClient(application, headers=bearer("user_headers"))
    for response in (client.get("/api/tasks"), TestClient(application, headers={}).get("/health")):
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
        assert "strict-transport-security" not in response.headers  # only in production
    assert client.get("/api/tasks").headers["cache-control"] == "no-store"
    unauthenticated = TestClient(application, headers={}).get("/api/tasks")
    assert unauthenticated.headers["cache-control"] == "no-store"


def test_production_adds_hsts_and_keeps_the_oauth_callback_headers():
    app = create_app(production(**google()))
    try:
        client = TestClient(app, headers={}, follow_redirects=False)
        response = client.get(f"{BASE}/callback")  # no state: rejected before any database use
        assert response.status_code == 303
        assert response.headers["strict-transport-security"].startswith("max-age=31536000")
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert response.headers["location"] == f"{ORIGIN}/calendar?google=invalid_state"
    finally:
        app.state.engine.dispose()


def test_production_without_cors_origins_allows_no_cross_origin_browser_calls():
    app = create_app(production())
    try:
        client = TestClient(app, headers={})
        preflight = client.options("/api/tasks", headers={
            "Origin": "https://evil.example", "Access-Control-Request-Method": "GET",
        })
        assert "access-control-allow-origin" not in preflight.headers
    finally:
        app.state.engine.dispose()


def test_session_tokens_are_checked_against_the_production_origin():
    app = create_app(production(clerk_jwt_key=PUBLIC_KEY, clerk_secret_key=None))
    try:
        # A token minted for the development origin is refused by the production server.
        assert AUTHORIZED_ORIGIN != ORIGIN
        response = TestClient(app, headers=bearer("user_x")).get("/api/tasks")
        assert response.status_code == 401
    finally:
        app.state.engine.dispose()
