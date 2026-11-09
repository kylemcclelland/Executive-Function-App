# ruff: noqa: E501
"""sqlite_to_postgres.py: filling a target that only holds the empty account row made by signing in."""

import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import backup_postgres  # noqa: E402
import sqlite_to_postgres  # noqa: E402
from test_backup import counts, seed  # noqa: E402

from app.core.config import LEGACY_USER_ID  # noqa: E402

pytestmark = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="needs TEST_DATABASE_URL")
BACKEND = Path(__file__).resolve().parents[1]
ACCOUNT = "user_new_staging_account"


@pytest.fixture
def source(application, monkeypatch, tmp_path):
    """A SQLite file shaped like the local database: the legacy data plus a development account that owns only a Google connection."""
    seed(application.state.session_factory)
    monkeypatch.setenv("DATABASE_URL", application.state.settings.database_url)
    monkeypatch.setattr(sys, "argv", ["tool", "backup", "--out", str(tmp_path)])
    assert backup_postgres.main() == 0
    return next(tmp_path.glob("optima-pars-2*Z.sqlite"))


@pytest.fixture
def target():
    admin_url = os.environ["TEST_DATABASE_URL"]
    schema = f"target_{uuid4().hex}"
    admin = create_engine(admin_url)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = make_url(admin_url).update_query_dict({"options": f"-csearch_path={schema}"}).render_as_string(hide_password=False)
    engine = create_engine(url)
    config = Config(str(BACKEND / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    yield url, engine
    engine.dispose()
    with admin.begin() as connection:
        connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    admin.dispose()


def sign_in(engine, clerk_id=ACCOUNT, timezone="America/New_York"):
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO users (id, clerk_user_id, timezone, created_at, updated_at) VALUES (:id, :c, :tz, now(), now())"), {"id": uuid4(), "c": clerk_id, "tz": timezone})


def run(monkeypatch, capsys, source, url, *flags):
    monkeypatch.setattr(sys, "argv", ["tool", "--source", str(source), "--target", url, *flags])
    code = sqlite_to_postgres.main()
    return code, capsys.readouterr().out


def test_without_the_flag_a_signed_in_target_is_refused(source, target, monkeypatch, capsys):
    url, engine = target
    sign_in(engine)
    code, output = run(monkeypatch, capsys, source, url, "--execute")
    assert code == 1 and "not empty" in output
    assert counts(url) == {"users": 1}


def test_the_dry_run_with_the_flag_reports_the_plan_and_writes_nothing(source, target, monkeypatch, capsys):
    url, engine = target
    sign_in(engine)
    code, output = run(monkeypatch, capsys, source, url, "--allow-empty-accounts")
    assert code == 0 and "will be left untouched" in output and "Dry run only" in output
    assert "books" in output and counts(url) == {"users": 1}


def test_the_copy_leaves_the_signed_in_account_alone_and_skips_the_development_account(source, target, monkeypatch, capsys):
    url, engine = target
    sign_in(engine)
    code, output = run(monkeypatch, capsys, source, url, "--allow-empty-accounts", "--execute")
    assert code == 0, output
    assert "Every table matches the source exactly." in output and "left untouched" in output
    after = counts(url)
    assert after["users"] == 2 and after["books"] == 1 and after["tasks"] == 1       # the account row + the legacy user, and the legacy data
    assert "google_calendar_connections" not in after                                 # the development account's credentials stayed behind
    with engine.connect() as connection:
        rows = dict(connection.execute(text("SELECT coalesce(clerk_user_id, 'legacy'), id::text FROM users")).all())
    assert set(rows) == {ACCOUNT, "legacy"} and rows["legacy"] == str(LEGACY_USER_ID)


@pytest.mark.parametrize("problem", ["account_owns_data", "other_table_not_empty", "clerk_id_clash"])
def test_anything_unexpected_in_the_target_stops_the_copy(source, target, monkeypatch, capsys, problem):
    url, engine = target
    sign_in(engine, "user_prod_owner" if problem == "clerk_id_clash" else ACCOUNT)
    flags = ["--allow-empty-accounts", "--execute"]
    if problem == "account_owns_data":
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO tasks (id, user_id, title, status, created_at, updated_at) SELECT gen_random_uuid(), id, 'Real work', 'todo', now(), now() FROM users"))
    elif problem == "other_table_not_empty":
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO cover_service_state (name, updated_at) VALUES ('x', now())"))
    else:
        with engine.begin() as connection:
            connection.execute(text("UPDATE users SET clerk_user_id = 'user_prod_owner'"))
        flags.insert(0, "--keep-clerk-users")
    before = counts(url)
    code, output = run(monkeypatch, capsys, source, url, *flags)
    assert code == 1 and "STOP" in output, output
    assert counts(url) == before


def test_a_source_that_would_overwrite_a_non_clerk_user_is_refused(source, target, monkeypatch, capsys):
    url, engine = target
    with engine.begin() as connection:     # a legacy-style row in the target is not an "account" the flag may keep
        connection.execute(text("INSERT INTO users (id, timezone, created_at, updated_at) VALUES (:id, 'UTC', now(), now())"), {"id": uuid4()})
    code, output = run(monkeypatch, capsys, source, url, "--allow-empty-accounts", "--execute")
    assert code == 1 and "STOP" in output
