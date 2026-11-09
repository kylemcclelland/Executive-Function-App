import os
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from alembic import command
from alembic.config import Config
from clerk_tokens import AUTHORIZED_ORIGIN, PUBLIC_KEY, bearer
from cryptography.fernet import Fernet
from fake_google import CLIENT_ID, CLIENT_SECRET, REDIRECT_URI, FakeGoogle
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

# ASGI module import must receive an explicit test identity context.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", os.environ.get("TEST_DATABASE_URL", "sqlite://"))

from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def signed_in_by_default(monkeypatch):
    """Every TestClient carries a valid Clerk session token unless a test passes its own headers.

    The server still verifies a real signature; there is no test bypass in the application.
    """
    original = TestClient.__init__

    def init(self, *args, **kwargs):
        kwargs.setdefault("headers", bearer())
        original(self, *args, **kwargs)

    monkeypatch.setattr(TestClient, "__init__", init)


ENCRYPTION_KEY = Fernet.generate_key().decode()


@pytest.fixture
def fake_google():
    return FakeGoogle()


@pytest.fixture
def application(fake_google):
    test_url = os.getenv("TEST_DATABASE_URL")
    admin = None
    path = None
    schema = f"test_{uuid4().hex}"
    if test_url:
        admin = create_engine(test_url)
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        url = make_url(test_url).update_query_dict({"options": f"-csearch_path={schema}"})
        database_url = url.render_as_string(hide_password=False)
    else:
        cache = BACKEND / ".cache"
        cache.mkdir(exist_ok=True)
        path = cache / f"{schema}.sqlite"
        database_url = f"sqlite:///{path}"
    app = create_app(Settings(
        app_env="test", database_url=database_url, clerk_jwt_key=PUBLIC_KEY,
        clerk_authorized_parties=[AUTHORIZED_ORIGIN], google_client_id=CLIENT_ID,
        google_client_secret=CLIENT_SECRET, google_token_encryption_key=ENCRYPTION_KEY,
        google_redirect_uri=REDIRECT_URI, _env_file=None,
    ), google_transport=httpx.MockTransport(fake_google.handle))
    app.state.google.client.clock = lambda: fake_google.now
    config = Config(str(BACKEND / "alembic.ini"))
    with app.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    yield app
    app.state.engine.dispose()
    if admin is not None:
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
    if path is not None:
        path.unlink(missing_ok=True)


@pytest.fixture
def client(application):
    with TestClient(application) as client:
        yield client
