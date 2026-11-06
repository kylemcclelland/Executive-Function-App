import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

# ASGI module import must receive an explicit test identity context.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", os.environ.get("TEST_DATABASE_URL", "sqlite://"))

from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture
def application():
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
    app = create_app(Settings(app_env="test", database_url=database_url, _env_file=None))
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
