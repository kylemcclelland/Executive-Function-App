# ruff: noqa: E501, F811
"""Wording the owner typed in a message: stored exactly, replacing the earlier edition only where intended, never approved."""

import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select
from test_devotions import reader  # noqa: F401

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "seed_data"))

import seed_devotion_drafts as seed  # noqa: E402

from app.models import Devotion, DevotionEvent, PrayerText  # noqa: E402
from app.services.devotions import text_fingerprint  # noqa: E402

EXPECTED = (
    "O my God, I am heartily sorry for having offended Thee, and I detest all my sins because of Thy just punishments, but most of all because they offend Thee, "
    "my God, Who art all-good and deserving of all my love. I firmly resolve, with the help of Thy grace, to sin no more and to avoid the near occasions of sin."
)
BALTIMORE = next(t["body"] for t in json.loads((SCRIPTS / "seed_data" / "prayer_sources.json").read_text(encoding="utf-8"))["texts"] if t["devotion_slug"] == "act-of-contrition" and t["language"] == "en")


@pytest.fixture
def run(application, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", application.state.settings.database_url)

    def go(*flags):
        return seed.main(list(flags)), capsys.readouterr().out
    return go


def act_en(application):
    with application.state.session_factory() as db:
        return db.scalar(select(PrayerText).join(Devotion).where(Devotion.slug == "act-of-contrition", PrayerText.language == "en"))


def put_back_the_earlier_edition_approved(application):
    """The state a database seeded before this change is in, with the earlier edition approved by an editor."""
    with application.state.session_factory.begin() as db:
        row = db.scalar(select(PrayerText).join(Devotion).where(Devotion.slug == "act-of-contrition", PrayerText.language == "en"))
        old = seed.earlier_wording(("act-of-contrition", "main", "en"))
        for name in ("body", "source_title", "source_authority", "source_edition", "source_date", "source_url", "attribution", "license_status", "license_notes"):
            setattr(row, name, old[name])
        row.source_verified_by, row.source_verified_at = "user_editor", datetime.now(UTC)
        row.status, row.approved_by, row.approved_at, row.approved_hash = "approved", "user_approver", datetime.now(UTC), text_fingerprint(row)
        return row.id


def test_the_supplied_wording_is_exactly_what_was_given_and_unlike_the_earlier_edition():
    entry = seed.owner_supplied_texts()[0]
    assert entry["body"] == EXPECTED and entry["body"] != BALTIMORE
    assert "\n" not in entry["body"] and entry["body"] == entry["body"].strip()


def test_seeding_creates_the_supplied_text_unverified_unapproved_with_its_provenance_and_no_duplicate(application, run):
    assert run("--execute")[0] == 0
    with application.state.session_factory() as db:
        rows = list(db.scalars(select(PrayerText).join(Devotion).where(Devotion.slug == "act-of-contrition")))
    assert sorted((t.slot, t.language) for t in rows) == [("main", "en"), ("main", "la")]          # one English text, replaced rather than duplicated
    row = act_en(application)
    assert row.body == EXPECTED
    assert (row.status, row.license_status, row.source_title) == ("proposed", "unverified", "User-supplied text")
    assert row.source_verified_by is None and row.approved_by is None and row.approved_hash is None and row.source_url is None
    assert "message names no author" in row.license_notes and "Replaces the earlier cited edition" in row.license_notes
    assert hashlib.sha256(row.body.encode()).hexdigest() == re.search(r"wording SHA-256 ([0-9a-f]{64})", row.license_notes).group(1)
    assert hashlib.sha256(BALTIMORE.encode()).hexdigest() in row.license_notes                    # the replaced edition is identified by its hash


def test_a_database_holding_the_earlier_approved_edition_is_replaced_and_returned_to_proposed(application, run):
    run("--execute")
    text_id = put_back_the_earlier_edition_approved(application)
    code, output = run("--execute", "--apply-owner-supplied")
    assert code == 0 and "1 replaced (returned to proposed)" in output
    row = act_en(application)
    assert row.id == text_id and row.body == EXPECTED                                              # the same record, edited in place
    assert (row.status, row.approved_by, row.approved_at, row.approved_hash, row.source_verified_by, row.license_status) == ("proposed", None, None, None, None, "unverified")
    with application.state.session_factory() as db:
        events = [e for e in db.scalars(select(DevotionEvent).where(DevotionEvent.text_id == text_id)) if e.actor == "seed:owner-supplied-text"]
        assert len(events) == 1 and events[0].from_status == "approved" and events[0].to_status == "proposed"
        assert "body" in events[0].note and EXPECTED[:20] not in events[0].note and BALTIMORE[:20] not in events[0].note     # field names only, never wording
    code, output = run("--execute", "--apply-owner-supplied")                                       # again: nothing more to do
    assert "0 replaced" in output and "1 already current" in output


def test_a_dry_run_changes_nothing(application, run):
    run("--execute")
    text_id = put_back_the_earlier_edition_approved(application)
    code, output = run("--apply-owner-supplied")
    assert code == 0 and "would be replaced" in output and "Dry run only" in output
    with application.state.session_factory() as db:
        row = db.get(PrayerText, text_id)
        assert row.body == BALTIMORE and row.status == "approved"


def test_a_text_edited_since_is_never_replaced(application, run):
    run("--execute")
    with application.state.session_factory.begin() as db:
        row = db.scalar(select(PrayerText).join(Devotion).where(Devotion.slug == "act-of-contrition", PrayerText.language == "en"))
        row.body = "A reviewer's own wording"
        text_id = row.id
    code, output = run("--execute", "--apply-owner-supplied")
    assert code == 0 and "skipped act-of-contrition: wording differs from the earlier edition" in output
    with application.state.session_factory() as db:
        assert db.get(PrayerText, text_id).body == "A reviewer's own wording"


def test_the_earlier_cited_record_is_kept_in_the_sources_file():
    assert seed.earlier_wording(("act-of-contrition", "main", "en"))["body"] == BALTIMORE
    assert "pains of hell" in BALTIMORE                                                           # it is the different, earlier edition


def test_the_supplied_text_is_readable_in_the_library_with_its_source_and_rights_unverified(application, run, reader):
    run("--execute")
    texts = {t["language"]: t for t in reader.get("/api/devotions/act-of-contrition").json()["texts"]}
    assert texts["en"]["body"] == EXPECTED and texts["en"]["has_wording"] is True
    assert texts["en"]["source"]["title"] == "User-supplied text" and texts["en"]["source"]["license_status"] == "unverified"
    assert texts["la"]["has_wording"] is False and texts["la"]["body"] == ""                       # the Latin is a citation only, labelled as such
