# ruff: noqa: E501
"""The devotion library: every devotion and every prayer text is readable by a signed-in user, with its source; bookmarks are
private to their owner; the retired editorial endpoints are gone. Every prayer text below is neutral test filler."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from clerk_tokens import bearer
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.models import Devotion, DevotionBookmark, PrayerText

READER, OTHER_READER = "user_reader", "user_other_reader"
MARKER = "FILLER-WORDING-ONE"
BODY = f"  {MARKER} first line  \n\nsecond paragraph\n\t\tindented line\n\n\n℣. versicle filler\n℟. response filler\n"
SOURCE = {
    "source_title": "A Test Source Book", "source_edition": "1st test edition",
    "attribution": "Filler attribution line", "license_status": "public_domain",
}


def as_(application, subject):
    return TestClient(application, headers=bearer(subject))


@pytest.fixture
def reader(application):
    return as_(application, READER)


@pytest.fixture
def other_reader(application):
    return as_(application, OTHER_READER)


def add_devotion(application, slug="test-devotion", *, texts=(), steps=(), **fields):
    """Put a devotion (and texts, as (slot, language, body) triples) straight into the database."""
    with application.state.session_factory.begin() as db:
        devotion = Devotion(
            slug=slug, title=fields.pop("title", "Prayer Title"), overview="Overview filler", references=[],
            instructions=[], steps=list(steps), status=fields.pop("status", "proposed"), created_by="test", **fields,
        )
        if devotion.status == "published":      # the database refuses a published row without its (historical) approval record
            devotion.approved_by, devotion.approved_at, devotion.approved_hash, devotion.published_at = "test", datetime.now(UTC), "x", datetime.now(UTC)
        db.add(devotion)
        for slot, language, body in texts:
            db.add(PrayerText(devotion=devotion, slot=slot, language=language, body=body, entered_by="test", **{**SOURCE, "license_status": "unverified" if not body else "public_domain"}))
        db.flush()
        return str(devotion.id)


# ---- Reading --------------------------------------------------------------------------------------
def test_a_fresh_library_is_empty(application, reader):
    assert reader.get("/api/devotions").json() == []
    assert reader.get("/api/devotions/nothing-here").status_code == 404


def test_every_devotion_is_listed_whatever_its_old_status_and_with_or_without_wording(application, reader):
    add_devotion(application, "drafted", title="B draft", texts=[("main", "en", "Some filler")])
    add_devotion(application, "published-once", title="A old", status="published", texts=[("main", "en", "Other filler")])
    add_devotion(application, "citation-only", title="C citation", texts=[("main", "en", "")])
    add_devotion(application, "nothing-yet", title="D empty")
    listing = reader.get("/api/devotions").json()
    assert [(d["slug"], d["has_text"]) for d in listing] == [("published-once", True), ("drafted", True), ("citation-only", False), ("nothing-yet", False)]


def test_the_exact_wording_is_returned_with_its_source_and_nothing_is_trimmed(application, reader):
    add_devotion(application, texts=[("main", "en", BODY), ("main", "la", "Latin filler")])
    detail = reader.get("/api/devotions/test-devotion").json()
    by_language = {t["language"]: t for t in detail["texts"]}
    assert by_language["en"]["body"] == BODY and by_language["en"]["has_wording"] is True
    assert by_language["la"]["body"] == "Latin filler"
    assert by_language["en"]["source"]["title"] == "A Test Source Book" and by_language["en"]["source"]["license_status"] == "public_domain"
    assert "license_notes" not in by_language["en"] and "approved_by" not in by_language["en"] and "status" not in by_language["en"]


def test_a_citation_only_record_is_marked_and_holds_no_wording(application, reader):
    add_devotion(application, texts=[("main", "en", "Filler wording"), ("main", "la", "")])
    texts = {t["language"]: t for t in reader.get("/api/devotions/test-devotion").json()["texts"]}
    assert texts["la"]["has_wording"] is False and texts["la"]["body"] == "" and texts["la"]["source"]["title"] == "A Test Source Book"
    assert texts["en"]["has_wording"] is True


def test_a_devotion_that_reuses_a_prayer_gets_that_prayer_from_the_other_devotion(application, reader):
    add_devotion(application, "prayer-one", texts=[("main", "en", "Reused filler"), ("main", "la", "Reusa filler")])
    add_devotion(application, "sequence", texts=[("own", "en", "Own filler")], steps=[
        {"kind": "prayer", "title": "One", "instruction": None, "text_slot": "main", "devotion_slug": "prayer-one", "repeat": None, "section": None, "group": None, "optional": False},
    ])
    texts = reader.get("/api/devotions/sequence").json()["texts"]
    assert sorted((t["devotion_slug"], t["slot"], t["language"]) for t in texts) == [("prayer-one", "main", "en"), ("prayer-one", "main", "la"), ("sequence", "own", "en")]


def test_a_text_not_named_by_a_step_is_not_pulled_in_from_another_devotion(application, reader):
    add_devotion(application, "other", texts=[("main", "en", "Other filler"), ("extra", "en", "Unrelated filler")])
    add_devotion(application, "sequence", steps=[
        {"kind": "prayer", "title": "One", "instruction": None, "text_slot": "main", "devotion_slug": "other", "repeat": None, "section": None, "group": None, "optional": False},
    ])
    assert [t["slot"] for t in reader.get("/api/devotions/sequence").json()["texts"]] == ["main"]


# ---- Signed-in only -------------------------------------------------------------------------------------
def test_the_library_needs_a_signed_in_user(application):
    add_devotion(application, texts=[("main", "en", "Filler wording")])
    anonymous = TestClient(application, headers={})
    for method, url in (("get", "/api/devotions"), ("get", "/api/devotions/test-devotion"), ("put", "/api/devotions/test-devotion/bookmark"), ("delete", "/api/devotions/test-devotion/bookmark")):
        response = getattr(anonymous, method)(url)
        assert response.status_code == 401 and "Filler wording" not in response.text


# ---- Bookmarks ----------------------------------------------------------------------------------------------
def test_bookmarks_toggle_and_are_idempotent(application, reader):
    add_devotion(application, texts=[("main", "en", "Filler wording")])
    assert reader.put("/api/devotions/test-devotion/bookmark").json() == {"bookmarked": True}
    assert reader.put("/api/devotions/test-devotion/bookmark").json() == {"bookmarked": True}
    assert reader.get("/api/devotions").json()[0]["bookmarked"] is True and reader.get("/api/devotions/test-devotion").json()["bookmarked"] is True
    with application.state.session_factory() as db:
        assert len(list(db.scalars(select(DevotionBookmark)))) == 1
    assert reader.delete("/api/devotions/test-devotion/bookmark").json() == {"bookmarked": False}
    assert reader.delete("/api/devotions/test-devotion/bookmark").json() == {"bookmarked": False}
    assert reader.get("/api/devotions").json()[0]["bookmarked"] is False


def test_a_bookmark_is_private_to_its_owner(application, reader, other_reader):
    add_devotion(application, texts=[("main", "en", "Filler wording")])
    reader.put("/api/devotions/test-devotion/bookmark")
    assert other_reader.get("/api/devotions").json()[0]["bookmarked"] is False
    assert other_reader.get("/api/devotions/test-devotion").json()["bookmarked"] is False
    other_reader.delete("/api/devotions/test-devotion/bookmark")                          # cannot remove someone else's
    assert reader.get("/api/devotions/test-devotion").json()["bookmarked"] is True


def test_bookmarking_a_devotion_that_does_not_exist_is_a_404(reader):
    assert reader.put("/api/devotions/nothing-here/bookmark").status_code == 404


# ---- The broad editorial workflow is retired; what exists now is the owner-only dashboard ------------------------
@pytest.mark.parametrize("path", ["/api/editorial/devotions", "/api/editorial-access", "/api/editorial/devotions/00000000-0000-0000-0000-000000000000/preview"])
def test_editorial_paths_are_closed_to_a_former_editor(application, path):
    """The old editor role grants nothing: editorial paths answer 403 (owner-only), 404 or 405 — never content."""
    assert as_(application, "user_editor").get(path).status_code in (403, 404, 405)


def test_no_editor_or_approver_setting_is_needed_or_read():
    settings = Settings(_env_file=None, app_env="development", database_url="sqlite://", editor_clerk_user_ids=["user_x"])
    assert not hasattr(settings, "editor_clerk_user_ids") and not hasattr(settings, "approver_clerk_user_ids")
    source = (Path(__file__).resolve().parents[1] / "app").rglob("*.py")
    assert not [str(path) for path in source if "editor_clerk_user_ids" in path.read_text(encoding="utf-8")]


def test_the_stored_history_is_left_alone_by_reading(application, reader):
    add_devotion(application, texts=[("main", "en", "Filler wording")])
    with application.state.session_factory() as db:
        before = [(t.status, t.approved_by, t.source_verified_by) for t in db.scalars(select(PrayerText))]
    reader.get("/api/devotions")
    reader.get("/api/devotions/test-devotion")
    with application.state.session_factory() as db:
        assert [(t.status, t.approved_by, t.source_verified_by) for t in db.scalars(select(PrayerText))] == before
