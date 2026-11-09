# ruff: noqa: E501
"""The PostgreSQL backup tool. Tests that need a real PostgreSQL run when TEST_DATABASE_URL is set
(see README: PostgreSQL-backed tests); the safety checks run everywhere."""

import json
import os
import sys
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import backup_postgres  # noqa: E402
import sqlite_to_postgres  # noqa: E402

from app.core.config import LEGACY_USER_ID  # noqa: E402
from app.models import (  # noqa: E402
    Book,
    GoogleCalendarConnection,
    GoogleOAuthState,
    InboxItem,
    Milestone,
    Note,
    NoteLink,
    NoteTag,
    Project,
    Step,
    Task,
    User,
)

needs_postgres = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="needs TEST_DATABASE_URL (a disposable PostgreSQL)"
)
BACKEND = Path(__file__).resolve().parents[1]


def run(monkeypatch, capsys, *arguments, url=None):
    if url is not None:
        monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr(sys, "argv", ["tool", *arguments])
    code = backup_postgres.main()
    return code, capsys.readouterr().out


def seed(session_factory):
    """Realistic rows across the schema: a legacy user, linked accounts, relationships, JSON, Unicode."""
    owner = uuid4()
    with session_factory.begin() as db:
        db.add_all([
            User(id=LEGACY_USER_ID, timezone="UTC"),
            User(id=owner, clerk_user_id="user_prod_owner", timezone="America/New_York"),
        ])
        db.flush()
        project = Project(user_id=LEGACY_USER_ID, name="Aquinas essay", description="Ünïcode ✝")
        db.add(project)
        db.flush()
        milestone = Milestone(user_id=LEGACY_USER_ID, project_id=project.id, title="Outline")
        task = Task(user_id=LEGACY_USER_ID, title="Draft", project_id=project.id, due_date=date(2026, 12, 1))
        db.add_all([milestone, task])
        db.flush()
        db.add_all([
            Step(task_id=task.id, title="Objections", position=0),
            InboxItem(user_id=LEGACY_USER_ID, content="A thought", converted_task_id=task.id, status="processed"),
        ])
        book = Book(user_id=LEGACY_USER_ID, title="Confessions", authors=["Augustine", "Maria Théotokos"])
        db.add(book)
        db.flush()
        a = Note(user_id=LEGACY_USER_ID, title="Restless", content="…", book_id=book.id)
        b = Note(user_id=LEGACY_USER_ID, title="Rest", content="x")
        db.add_all([a, b])
        db.flush()
        db.add_all([
            NoteTag(note_id=a.id, tag="grace"),
            NoteLink(user_id=LEGACY_USER_ID, source_note_id=a.id, target_note_id=b.id, link_type="supports"),
            GoogleCalendarConnection(
                user_id=owner, encrypted_refresh_token="gAAAAAB-encrypted-not-plaintext",
                google_account_email="owner@example.com", connection_status="active",
            ),
            GoogleOAuthState(
                user_id=owner, state_hash="a" * 64, encrypted_code_verifier="enc",
                expires_at=__import__("datetime").datetime(2030, 1, 1, tzinfo=__import__("datetime").UTC),
            ),
        ])
    return owner


def counts(url):
    engine = create_engine(url)
    with engine.connect() as connection:
        out = {t.name: n for t in backup_postgres.Base.metadata.sorted_tables
               if (n := connection.execute(text(f'SELECT count(*) FROM "{t.name}"')).scalar())}
    engine.dispose()
    return out


# ------------------------------------------------------------------ safety, runs everywhere

def test_it_refuses_sqlite_and_a_missing_url(monkeypatch, capsys, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(SystemExit, match="DATABASE_URL"):
        run(monkeypatch, capsys, "backup", "--out", str(tmp_path))
    with pytest.raises(SystemExit, match="PostgreSQL only"):
        run(monkeypatch, capsys, "backup", "--out", str(tmp_path), url="sqlite:///data/executive_function.db")
    assert list(tmp_path.iterdir()) == []


def test_the_database_url_is_never_taken_from_the_command_line(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(sys, "argv", ["tool", "backup", "--out", str(tmp_path), "--url", "postgresql://x"])
    with pytest.raises(SystemExit):
        backup_postgres.main()


def test_verify_needs_both_files(monkeypatch, capsys, tmp_path):
    lonely = tmp_path / "optima-pars-20261109T000000Z.sqlite"
    lonely.write_bytes(b"")
    code, output = run(monkeypatch, capsys, "verify", str(lonely))
    assert code == 2 and "manifest" in output


# ------------------------------------------------------------------ PostgreSQL

@needs_postgres
def test_backup_verifies_and_leaves_the_database_untouched(application, monkeypatch, capsys, tmp_path):
    url = application.state.settings.database_url
    seed(application.state.session_factory)
    before = counts(url)
    code, output = run(monkeypatch, capsys, "backup", "--out", str(tmp_path), url=url)
    assert code == 0, output
    (backup,) = tmp_path.glob("optima-pars-*.sqlite")
    manifest = json.loads(backup.with_suffix(".manifest.json").read_text())
    assert manifest["alembic_revision"] == ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini"))).get_current_head()
    assert manifest["tables"]["books"]["rows"] == 1 and manifest["tables"]["users"]["rows"] == 2
    assert manifest["file"]["bytes"] == backup.stat().st_size
    assert counts(url) == before                                      # the source never changed
    assert list(tmp_path.glob("*.partial")) == []                     # nothing half-written left over
    password = make_url(url).password
    assert not password or password not in output + json.dumps(manifest)   # no secret in output or manifest
    code, output = run(monkeypatch, capsys, "verify", str(backup))
    assert code == 0 and output.startswith("OK")


def present_counts(url) -> dict[str, int]:
    """Row counts for the tables the database actually has (counts() assumes it matches the code)."""
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            names = inspect(connection).get_table_names()
            return {name: connection.execute(text(f'SELECT count(*) FROM "{name}"')).scalar() for name in sorted(names)}
    finally:
        engine.dispose()


@needs_postgres
def test_a_database_one_migration_behind_the_code_can_be_backed_up_and_verified(application, monkeypatch, capsys, tmp_path):
    """The backup taken just before a migration: the code already knows tables the database lacks."""
    url = application.state.settings.database_url
    seed(application.state.session_factory)
    config = Config(str(BACKEND / "alembic.ini"))
    with application.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0009")
    before = present_counts(url)
    code, output = run(monkeypatch, capsys, "backup", "--out", str(tmp_path), url=url)
    assert code == 0, output
    (backup,) = tmp_path.glob("optima-pars-*.sqlite")
    manifest = json.loads(backup.with_suffix(".manifest.json").read_text())
    assert manifest["alembic_revision"] == "0009"
    assert manifest["absent_tables"] == ["devotion_bookmarks", "devotion_events", "devotions", "prayer_texts"]
    assert not {"devotions", "prayer_texts"} & set(manifest["tables"])
    assert manifest["tables"]["books"]["rows"] == 1 and manifest["tables"]["users"]["rows"] == 2
    assert present_counts(url) == before and list(tmp_path.glob("*.partial")) == []
    code, output = run(monkeypatch, capsys, "verify", str(backup))
    assert code == 0 and output.startswith("OK")
    assert "behind the code" in run(monkeypatch, capsys, "backup", "--out", str(tmp_path / "again"), url=url)[1]


@needs_postgres
def test_the_backup_is_a_consistent_snapshot_even_while_the_app_writes(application, monkeypatch, capsys, tmp_path):
    url = application.state.settings.database_url
    seed(application.state.session_factory)
    original = backup_postgres.alembic_revision
    done = []

    def revision_then_a_concurrent_write(connection):
        value = original(connection)           # the snapshot starts with this first query
        if connection.dialect.name == "postgresql" and not done:
            done.append(True)
            with application.state.session_factory.begin() as db:   # another connection commits later
                db.add(User(id=uuid4(), clerk_user_id="user_arrived_mid_backup", timezone="UTC"))
        return value

    monkeypatch.setattr(backup_postgres, "alembic_revision", revision_then_a_concurrent_write)
    code, output = run(monkeypatch, capsys, "backup", "--out", str(tmp_path), url=url)
    assert code == 0, output
    manifest = json.loads(next(tmp_path.glob("*.manifest.json")).read_text())
    assert manifest["tables"]["users"]["rows"] == 2              # the late row is not in the snapshot
    assert counts(url)["users"] == 3                              # ...but it is safely in the database


@needs_postgres
def test_tampering_is_detected(application, monkeypatch, capsys, tmp_path):
    url = application.state.settings.database_url
    seed(application.state.session_factory)
    assert run(monkeypatch, capsys, "backup", "--out", str(tmp_path), url=url)[0] == 0
    backup = next(tmp_path.glob("*.sqlite"))
    original = backup.read_bytes()
    import sqlite3
    with sqlite3.connect(backup) as connection:
        connection.execute("UPDATE books SET title = 'Altered'")
    code, output = run(monkeypatch, capsys, "verify", str(backup))
    assert code == 1 and "SHA-256" in output
    backup.write_bytes(original)
    assert run(monkeypatch, capsys, "verify", str(backup))[0] == 0
    manifest = backup.with_suffix(".manifest.json")
    data = json.loads(manifest.read_text())
    data["tables"]["tasks"]["rows"] += 1
    manifest.write_text(json.dumps(data))
    code, output = run(monkeypatch, capsys, "verify", str(backup))
    assert code == 1 and "tasks" in output


@needs_postgres
def test_a_backup_that_does_not_verify_is_discarded(application, monkeypatch, capsys, tmp_path):
    seed(application.state.session_factory)
    monkeypatch.setattr(backup_postgres, "verify_backup", lambda path, manifest: ["simulated corruption"])
    code, output = run(monkeypatch, capsys, "backup", "--out", str(tmp_path),
                       url=application.state.settings.database_url)
    assert code == 1 and "discarded" in output
    assert list(tmp_path.iterdir()) == []


@needs_postgres
def test_old_backups_are_pruned_but_unrelated_files_are_not(application, monkeypatch, capsys, tmp_path):
    for stamp in ("20250101T000000Z", "20250102T000000Z", "20250103T000000Z", "20250104T000000Z"):
        (tmp_path / f"optima-pars-{stamp}.sqlite").write_bytes(b"old")
        (tmp_path / f"optima-pars-{stamp}.manifest.json").write_text("{}")
    (tmp_path / "notes.txt").write_text("keep me")
    (tmp_path / "optima-pars-latest.sqlite").write_text("not ours")
    code, output = run(monkeypatch, capsys, "backup", "--out", str(tmp_path), "--keep", "2",
                       url=application.state.settings.database_url)
    assert code == 0 and "pruned" in output
    names = sorted(p.name for p in tmp_path.iterdir())
    assert "notes.txt" in names and "optima-pars-latest.sqlite" in names
    ours = [n for n in names if backup_postgres.PATTERN.match(n)]
    assert len(ours) == 2 and "optima-pars-20250104T000000Z.sqlite" in ours   # the new one + the newest old one


@needs_postgres
def test_restoring_a_backup_reproduces_every_row_in_a_fresh_database(application, monkeypatch, capsys, tmp_path):
    """The restore drill: backup, then load into an empty migrated database and compare everything."""
    url = application.state.settings.database_url
    owner = seed(application.state.session_factory)
    assert run(monkeypatch, capsys, "backup", "--out", str(tmp_path), url=url)[0] == 0
    backup = next(tmp_path.glob("*.sqlite"))

    admin_url = os.environ["TEST_DATABASE_URL"]
    schema = f"restore_{uuid4().hex}"
    admin = create_engine(admin_url)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    target_url = make_url(admin_url).update_query_dict({"options": f"-csearch_path={schema}"}).render_as_string(hide_password=False)
    try:
        config = Config(str(BACKEND / "alembic.ini"))
        engine = create_engine(target_url)
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        engine.dispose()
        monkeypatch.setattr(sys, "argv", ["tool", "--source", str(backup), "--target", target_url, "--keep-clerk-users", "--execute"])
        assert sqlite_to_postgres.main() == 0
        assert "Every table matches the source exactly" in capsys.readouterr().out
        assert counts(target_url) == counts(url)
        engine = create_engine(target_url)
        with engine.connect() as connection:
            assert connection.execute(text("SELECT clerk_user_id FROM users WHERE clerk_user_id IS NOT NULL")).scalar() == "user_prod_owner"
            assert connection.execute(text("SELECT count(*) FROM google_calendar_connections")).scalar() == 1
        engine.dispose()
    finally:
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
    assert owner
