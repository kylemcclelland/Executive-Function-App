# ruff: noqa: E501
"""Web Push subscriptions: registration, refresh, removal, validation, user isolation and the unconfigured server."""

from clerk_tokens import bearer
from fastapi.testclient import TestClient
from pydantic import SecretStr
from pytest import fixture
from sqlalchemy import select

from app.models import PushSubscription

SUBSCRIPTION = {
    "endpoint": "https://push.example.com/send/abc123",
    "keys": {"p256dh": "BPubKey_123-abc", "auth": "authSecret_1-2"},
}


@fixture
def application_with_push(application):
    """The same temporary-database application, with VAPID keys configured (test values only)."""
    application.state.settings.vapid_public_key = "test-public-key"
    application.state.settings.vapid_private_key = SecretStr("test-private-key")
    application.state.settings.vapid_subject = "mailto:test@example.org"
    return application


def user(application, name):
    return TestClient(application, headers=bearer(name))


def test_push_is_reported_unconfigured_without_vapid_keys(application):
    client = TestClient(application)
    config = client.get("/api/push/config")
    assert config.status_code == 200
    assert config.json() == {"configured": False, "public_key": None}
    assert client.post("/api/push/subscriptions", json=SUBSCRIPTION).status_code == 503
    status = client.get("/api/push/status").json()
    assert status["configured"] is False and status["subscription_count"] == 0


def test_config_exposes_only_the_public_key(application_with_push):
    client = TestClient(application_with_push)
    config = client.get("/api/push/config").json()
    assert config["configured"] is True
    assert config["public_key"] == "test-public-key"
    assert "private" not in str(config).lower()


def test_register_refresh_and_remove_a_subscription(application_with_push):
    client = TestClient(application_with_push)
    created = client.post("/api/push/subscriptions", json=SUBSCRIPTION)
    assert created.status_code == 201
    assert created.json()["refreshed"] is False

    # The same browser registering again refreshes in place: no duplicate row.
    again = client.post("/api/push/subscriptions", json={**SUBSCRIPTION, "keys": {"p256dh": "BRotatedKey", "auth": "rotatedAuth"}})
    assert again.status_code == 201 and again.json()["refreshed"] is True
    assert again.json()["id"] == created.json()["id"]
    assert client.get("/api/push/status").json()["subscription_count"] == 1
    with application_with_push.state.session_factory() as db:
        row = db.scalar(select(PushSubscription))
        assert row.p256dh == "BRotatedKey"

    # A second browser is a second subscription for the same user.
    other = {"endpoint": "https://push.example.com/send/other", "keys": SUBSCRIPTION["keys"]}
    assert client.post("/api/push/subscriptions", json=other).status_code == 201
    assert client.get("/api/push/status").json()["subscription_count"] == 2

    assert client.request("DELETE", "/api/push/subscriptions", json={"endpoint": SUBSCRIPTION["endpoint"]}).status_code == 204
    assert client.get("/api/push/status").json()["subscription_count"] == 1
    # Removing it again is harmless.
    assert client.request("DELETE", "/api/push/subscriptions", json={"endpoint": SUBSCRIPTION["endpoint"]}).status_code == 204


def test_users_cannot_see_or_remove_each_other(application_with_push):
    alice, mallory = user(application_with_push, "user_alice"), user(application_with_push, "user_mallory")
    assert alice.post("/api/push/subscriptions", json=SUBSCRIPTION).status_code == 201
    # Mallory's status never counts Alice's browser, and deleting by Alice's endpoint removes nothing.
    assert mallory.get("/api/push/status").json()["subscription_count"] == 0
    assert mallory.request("DELETE", "/api/push/subscriptions", json={"endpoint": SUBSCRIPTION["endpoint"]}).status_code == 204
    assert alice.get("/api/push/status").json()["subscription_count"] == 1
    # A second account signing in on the same browser takes the endpoint over instead of duplicating it.
    assert mallory.post("/api/push/subscriptions", json=SUBSCRIPTION).status_code == 201
    assert mallory.get("/api/push/status").json()["subscription_count"] == 1
    assert alice.get("/api/push/status").json()["subscription_count"] == 0


def test_subscription_input_is_validated(application_with_push):
    client = TestClient(application_with_push)
    bad = [
        {**SUBSCRIPTION, "endpoint": "http://push.example.com/insecure"},
        {**SUBSCRIPTION, "endpoint": "javascript:alert(1)"},
        {**SUBSCRIPTION, "endpoint": "https://user:pass@push.example.com/send/x"},
        {**SUBSCRIPTION, "endpoint": "https://push.example.com/" + "x" * 2000},
        {**SUBSCRIPTION, "keys": {"p256dh": "not base64url!!", "auth": "ok"}},
        {**SUBSCRIPTION, "keys": {"p256dh": "", "auth": "ok"}},
        {"endpoint": SUBSCRIPTION["endpoint"]},
    ]
    for body in bad:
        assert client.post("/api/push/subscriptions", json=body).status_code == 422, body


def test_push_requires_authentication(application_with_push):
    client = TestClient(application_with_push, headers={})
    for method, path in (("GET", "/api/push/config"), ("GET", "/api/push/status"), ("POST", "/api/push/subscriptions"), ("DELETE", "/api/push/subscriptions")):
        assert client.request(method, path).status_code in (401, 403), (method, path)


def test_migration_0014_creates_and_drops_the_table(application):
    from pathlib import Path

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect

    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with application.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        assert "push_subscriptions" in inspect(connection).get_table_names()
        columns = {column["name"] for column in inspect(connection).get_columns("push_subscriptions")}
        assert {"id", "user_id", "endpoint", "endpoint_hash", "p256dh", "auth", "failure_count", "last_failure_at", "created_at", "updated_at"} <= columns
        command.downgrade(config, "0013")
        assert "push_subscriptions" not in inspect(connection).get_table_names()
        # Existing Rule of Life tables are untouched by the downgrade.
        assert "rule_of_life_entries" in inspect(connection).get_table_names()
        command.upgrade(config, "head")
        assert "push_subscriptions" in inspect(connection).get_table_names()
