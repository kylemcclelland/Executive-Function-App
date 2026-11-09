# ruff: noqa: E501
"""The ownership-transfer tool: it must refuse everything that is not exactly the verified owner."""

import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from clerk_tokens import bearer
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select, text, update

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import backup_postgres  # noqa: E402
import claim_legacy_data as claim  # noqa: E402

from app.core.config import LEGACY_USER_ID  # noqa: E402
from app.models import Book, InboxItem, Note, Project, Task, User  # noqa: E402

OWNER = "user_prod_owner"
EMAIL = "owner@example.com"
needs_postgres = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="needs TEST_DATABASE_URL")


class Env:
    """A database with legacy data, a faked Clerk, and a matching fresh backup."""

    def __init__(self, application, monkeypatch, tmp_path, capsys):
        self.application, self.monkeypatch, self.tmp_path, self.capsys = application, monkeypatch, tmp_path, capsys
        self.url = application.state.settings.database_url
        self.clerk = {OWNER: self.clerk_user(OWNER, EMAIL)}
        monkeypatch.setenv("DATABASE_URL", self.url)
        monkeypatch.setenv("CLERK_SECRET_KEY", "sk_live_dummy")
        monkeypatch.setattr(claim, "fetch_clerk_user", self.fetch)
        monkeypatch.setattr(claim, "verify_backup", lambda path, manifest: self.backup_problems)
        self.backup_problems = []
        self.seed()

    @staticmethod
    def clerk_user(user_id, email, verified=True):
        return {"id": user_id, "first_name": "Marcus", "last_name": "Aurelius", "primary_email_address_id": "idn_1",
                "email_addresses": [{"id": "idn_1", "email_address": email, "verification": {"status": "verified" if verified else "unverified"}}],
                "created_at": 1_700_000_000_000, "last_sign_in_at": 1_700_000_500_000}

    def fetch(self, key, user_id):
        if user_id not in self.clerk:
            raise claim.Refused(f"Clerk has no user {user_id} in the instance this secret key belongs to.")
        return self.clerk[user_id]

    def seed(self):
        with self.application.state.session_factory.begin() as db:
            db.add(User(id=LEGACY_USER_ID, timezone="UTC"))
            db.flush()
            project = Project(user_id=LEGACY_USER_ID, name="Kept")
            db.add(project)
            db.flush()
            task = Task(user_id=LEGACY_USER_ID, title="Kept task", project_id=project.id)
            db.add(task)
            db.flush()
            db.add_all([Book(user_id=LEGACY_USER_ID, title="Confessions", authors=["Augustine"]),
                        Note(user_id=LEGACY_USER_ID, title="A note", content="x"),
                        InboxItem(user_id=LEGACY_USER_ID, content="thought")])

    def sign_in_once(self, timezone="America/Chicago"):
        """What the first production sign-in does: creates an empty account row for the Clerk id."""
        with self.application.state.session_factory.begin() as db:
            db.add(User(id=uuid4(), clerk_user_id=OWNER, timezone=timezone))

    def backup(self, age=timedelta(0), drift=None):
        engine = create_engine(self.url)
        with engine.connect() as connection:
            totals = claim.table_totals(connection)
        engine.dispose()
        if drift:
            totals[drift] += 1
        file = self.tmp_path / "optima-pars-20261109T000000Z.sqlite"
        file.write_bytes(b"stand-in")
        manifest = {"format": 1, "created_at_utc": (datetime.now(UTC) - age).isoformat(), "alembic_revision": "0009",
                    "tables": {name: {"rows": n, "sha256": "x"} for name, n in totals.items()}}
        file.with_suffix(".manifest.json").write_text(json.dumps(manifest))
        return file

    def run(self, *arguments):
        self.monkeypatch.setattr(sys, "argv", ["tool", *arguments])
        code = claim.main()
        return code, self.capsys.readouterr().out

    def claim(self, *extra, file=None, email=EMAIL, instance="live", clerk_id=OWNER):
        file = file or self.backup()
        return self.run("claim", "--clerk-user-id", clerk_id, "--expect-email", email, "--instance", instance, "--backup", str(file), *extra)

    def rows(self):
        with self.application.state.session_factory() as db:
            return {u.clerk_user_id or "legacy": (u.id, u.timezone) for u in db.scalars(select(User))}

    def totals(self):
        engine = create_engine(self.url)
        with engine.connect() as connection:
            result = claim.table_totals(connection)
        engine.dispose()
        return result


@pytest.fixture
def env(application, monkeypatch, tmp_path, capsys):
    return Env(application, monkeypatch, tmp_path, capsys)


EXECUTE = ("--execute", "--confirm-clerk-id", OWNER)


# ------------------------------------------------------------------ inspect

def test_inspect_shows_who_clerk_says_the_account_is_and_changes_nothing(env):
    env.sign_in_once()
    before = env.totals()
    code, output = env.run("inspect", "--clerk-user-id", OWNER)
    assert code == 0
    assert "owner@example.com" in output and "verified" in output and "live instance" in output
    assert "legacy user      unlinked (claimable)" in output and "books 1" in output
    assert "If they are not the owner, STOP" in output
    assert env.totals() == before and "sk_live_dummy" not in output


def test_inspect_works_before_the_owner_has_signed_in(env):
    code, output = env.run("inspect", "--clerk-user-id", OWNER)
    assert code == 0 and "no account row yet" in output


def test_inspect_rejects_an_id_clerk_does_not_know(env):
    code, output = env.run("inspect", "--clerk-user-id", "user_nobody")
    assert code == 1 and "no user user_nobody" in output


# ------------------------------------------------------------------ the dry run

def test_a_dry_run_checks_everything_and_writes_nothing(env):
    env.sign_in_once()
    before, rows = env.totals(), env.rows()
    code, output = env.claim("--timezone", "account")
    assert code == 0 and "Dry run: all checks passed" in output
    assert "will be removed" in output and "owns" in output and "Data rows are not moved" in output
    assert env.totals() == before and env.rows() == rows


# ------------------------------------------------------------------ every refusal

@pytest.mark.parametrize("scenario, fragment", [
    ("wrong_email", "not the expected"),
    ("unverified", "has not verified"),
    ("wrong_instance", "belongs to the live one"),
    ("unknown_user", "no user"),
    ("already_linked", "already linked"),
    ("candidate_owns_data", "already owns data"),
    ("no_timezone_choice", "choose whose timezone"),
    ("stale_backup", "minutes old"),
    ("database_changed", "changed since the backup"),
    ("bad_backup", "does not verify"),
    ("missing_backup", "backup file"),
])
def test_it_refuses_unless_everything_checks_out(env, scenario, fragment):
    env.sign_in_once()
    arguments, kwargs = ["--timezone", "legacy"], {}
    if scenario == "wrong_email":
        kwargs["email"] = "someone.else@example.com"
    elif scenario == "unverified":
        env.clerk[OWNER] = env.clerk_user(OWNER, EMAIL, verified=False)
    elif scenario == "wrong_instance":
        kwargs["instance"] = "test"
    elif scenario == "unknown_user":
        kwargs["clerk_id"] = "user_stranger"
    elif scenario == "already_linked":
        with env.application.state.session_factory.begin() as db:
            db.execute(update(User).where(User.id == LEGACY_USER_ID).values(clerk_user_id="user_someone_else"))
            db.execute(delete(User).where(User.clerk_user_id == OWNER))
    elif scenario == "candidate_owns_data":
        with env.application.state.session_factory.begin() as db:
            account = db.scalar(select(User.id).where(User.clerk_user_id == OWNER))
            db.add(Task(user_id=account, title="Real work"))
    elif scenario == "no_timezone_choice":
        arguments = []
    elif scenario == "stale_backup":
        kwargs["file"] = env.backup(age=timedelta(hours=2))
    elif scenario == "database_changed":
        kwargs["file"] = env.backup(drift="books")
    elif scenario == "bad_backup":
        env.backup_problems = ["file SHA-256 differs from the manifest"]
    elif scenario == "missing_backup":
        kwargs["file"] = env.tmp_path / "nope.sqlite"
    before, rows = env.totals(), env.rows()
    code, output = env.claim(*arguments, *EXECUTE, **kwargs)
    assert code == 1 and fragment in output, output
    assert "REFUSED (nothing was changed)" in output or "REFUSED" in output
    assert env.totals() == before and env.rows() == rows             # not one row changed


def test_execute_needs_the_clerk_id_typed_twice(env):
    env.sign_in_once()
    before, rows = env.totals(), env.rows()
    code, output = env.claim("--timezone", "legacy", "--execute", "--confirm-clerk-id", "user_typo")
    assert code == 1 and "must repeat the Clerk id" in output
    code, output = env.claim("--timezone", "legacy", "--execute")
    assert code == 1
    assert env.totals() == before and env.rows() == rows


def test_missing_secret_key_or_database_is_refused(env):
    env.monkeypatch.delenv("CLERK_SECRET_KEY")
    assert env.claim("--timezone", "legacy")[0] == 1
    env.monkeypatch.setenv("CLERK_SECRET_KEY", "sk_live_dummy")
    env.monkeypatch.delenv("DATABASE_URL")
    assert env.claim("--timezone", "legacy")[0] == 1


# ------------------------------------------------------------------ the claim itself

def test_the_claim_links_the_legacy_data_and_removes_only_the_empty_account(env):
    env.sign_in_once()
    before = env.totals()
    code, output = env.claim("--timezone", "account", *EXECUTE)
    assert code == 0, output
    assert "Done." in output and "To undo" in output
    rows = env.rows()
    assert set(rows) == {OWNER} and rows[OWNER] == (LEGACY_USER_ID, "America/Chicago")
    after = env.totals()
    assert after.pop("users") == before.pop("users") - 1 and after == before     # nothing else moved

    owner = TestClient(env.application, headers=bearer(OWNER))
    assert owner.get("/api/books").json()["total"] == 1
    assert [t["title"] for t in owner.get("/api/tasks").json()] == ["Kept task"]
    assert len(owner.get("/api/projects").json()) == 1 and len(owner.get("/api/inbox").json()) == 1
    stranger = TestClient(env.application, headers=bearer("user_stranger"))
    assert stranger.get("/api/books").json()["total"] == 0 and stranger.get("/api/tasks").json() == []


def test_the_legacy_timezone_can_win_instead(env):
    env.sign_in_once("America/Chicago")
    assert env.claim("--timezone", "legacy", *EXECUTE)[0] == 0
    assert env.rows()[OWNER][1] == "UTC"


def test_the_empty_account_can_be_kept_unlinked_instead_of_removed(env):
    env.sign_in_once()
    before = env.totals()
    assert env.claim("--timezone", "legacy", "--unlink-empty", *EXECUTE)[0] == 0
    assert env.totals() == before
    assert set(env.rows()) == {OWNER, "legacy"} or len(env.rows()) == 2
    with env.application.state.session_factory() as db:
        assert db.scalar(select(User.clerk_user_id).where(User.id == LEGACY_USER_ID)) == OWNER
        assert db.scalar(text("SELECT count(*) FROM users WHERE clerk_user_id IS NULL")) == 1


def test_it_works_when_the_owner_has_not_signed_in_yet(env):
    assert env.claim(*EXECUTE)[0] == 0
    assert set(env.rows()) == {OWNER}


def test_a_second_claim_is_refused(env):
    env.sign_in_once()
    assert env.claim("--timezone", "legacy", *EXECUTE)[0] == 0
    code, output = env.claim("--timezone", "legacy", *EXECUTE)
    assert code == 1 and "already linked" in output


def test_a_failure_part_way_rolls_everything_back(env):
    env.sign_in_once()
    before, rows = env.totals(), env.rows()
    original = claim.table_totals

    def wrong_totals_after_the_change(connection):
        result = original(connection)
        linked = connection.execute(select(User.clerk_user_id).where(User.id == LEGACY_USER_ID)).scalar()
        if linked == OWNER:          # the check made after the writes: pretend a row vanished
            result["books"] -= 1
        return result

    env.monkeypatch.setattr(claim, "table_totals", wrong_totals_after_the_change)
    code, output = env.claim("--timezone", "legacy", *EXECUTE)
    assert code == 1 and "rolling everything back" in output
    env.monkeypatch.setattr(claim, "table_totals", original)
    assert env.totals() == before and env.rows() == rows


# ------------------------------------------------------------------ with a real backup, on PostgreSQL

@needs_postgres
def test_end_to_end_with_a_real_backup(application, monkeypatch, tmp_path, capsys):
    env = Env(application, monkeypatch, tmp_path, capsys)
    monkeypatch.undo()                                   # use the real verify_backup, not the stub
    monkeypatch.setenv("DATABASE_URL", env.url)
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_live_dummy")
    monkeypatch.setattr(claim, "fetch_clerk_user", env.fetch)
    env.sign_in_once()
    monkeypatch.setattr(sys, "argv", ["tool", "backup", "--out", str(tmp_path)])
    assert backup_postgres.main() == 0
    capsys.readouterr()
    real_backup = next(tmp_path.glob("optima-pars-2*Z.sqlite"), None)
    assert real_backup is not None
    code, output = env.run("claim", "--clerk-user-id", OWNER, "--expect-email", EMAIL, "--instance", "live", "--backup", str(real_backup), "--timezone", "account", *EXECUTE)
    assert code == 0, output
    assert set(env.rows()) == {OWNER}
