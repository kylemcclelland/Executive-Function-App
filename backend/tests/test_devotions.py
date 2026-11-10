# ruff: noqa: E501
"""Devotions: publication workflow, authorization, and the promise that unapproved wording never
reaches a reader. Every prayer text below is neutral test filler, never real devotional content."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from clerk_tokens import bearer
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.models import Devotion, PrayerText

EDITOR, APPROVER, BOTH, READER, OTHER_READER = (
    "user_editor", "user_approver", "user_both", "user_reader", "user_other_reader",
)
MARKER = "FILLER-WORDING-ONE"
BODY = f"  {MARKER} first line  \n\nsecond paragraph\n\t\tindented line\n\n\n℣. versicle filler\n℟. response filler\n"


@pytest.fixture(autouse=True)
def roles(application):
    application.state.settings.editor_clerk_user_ids = [EDITOR, BOTH]
    application.state.settings.approver_clerk_user_ids = [APPROVER, BOTH]


def as_(application, subject):
    return TestClient(application, headers=bearer(subject))


@pytest.fixture
def editor(application):
    return as_(application, EDITOR)


@pytest.fixture
def approver(application):
    return as_(application, APPROVER)


@pytest.fixture
def reader(application):
    return as_(application, READER)


BASE = "/api/editorial/devotions"
SOURCE = {
    "source_title": "A Test Source Book", "source_edition": "1st test edition",
    "attribution": "Filler attribution line", "license_status": "public_domain",
}


def make_devotion(editor, slug="test-devotion", **extra):
    response = editor.post(BASE, json={
        "slug": slug, "title": "Prayer Title", "overview": "Overview filler", **extra,
    })
    assert response.status_code == 201, response.text
    return response.json()


def make_text(editor, devotion, slot="main", language="en", body=BODY, **extra):
    fields = {"slot": slot, "language": language, "body": body, **SOURCE, **extra}
    response = editor.post(f"{BASE}/{devotion['id']}/texts", json=fields)
    assert response.status_code == 201, response.text
    return response.json()


def move(client, url, to, expect=200):
    response = client.post(url, json={"to": to})
    assert response.status_code == expect, response.text
    return response.json()


def approve_text(editor, approver, devotion, text_row):
    url = f"{BASE}/{devotion['id']}/texts/{text_row['id']}/transition"
    for step in ("source_verified", "pending_approval"):
        move(editor, url, step)
    return move(approver, url, "approved")


def publish(editor, approver, devotion):
    url = f"{BASE}/{devotion['id']}/transition"
    for step in ("source_verified", "pending_approval"):
        move(editor, url, step)
    move(approver, url, "approved")
    return move(approver, url, "published")


def published_with_text(editor, approver, slug="test-devotion", **text_extra):
    devotion = make_devotion(editor, slug)
    text_row = make_text(editor, devotion, **text_extra)
    approve_text(editor, approver, devotion, text_row)
    publish(editor, approver, devotion)
    return devotion, text_row


# ---- Nothing is published, and nothing is seeded ---------------------------------------------
def test_a_fresh_database_holds_no_devotions_or_prayer_texts(application, reader):
    with application.state.session_factory() as db:
        assert db.scalar(select(text("count(*)")).select_from(Devotion)) == 0
        assert db.scalar(select(text("count(*)")).select_from(PrayerText)) == 0
    assert reader.get("/api/devotions").json() == []


def test_the_migration_is_reversible_and_additive(application):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    tables = {"devotions", "prayer_texts", "devotion_events", "devotion_bookmarks"}
    with application.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0009")
        assert not tables & set(inspect(connection).get_table_names())
        assert "users" in inspect(connection).get_table_names()
        command.upgrade(config, "head")
        assert tables <= set(inspect(connection).get_table_names())


# ---- Authorization ----------------------------------------------------------------------------
def test_signing_in_is_not_enough_to_reach_the_editorial_interface(reader):
    assert reader.get(BASE).status_code == 403
    assert reader.post(BASE, json={"slug": "x", "title": "T", "overview": "O"}).status_code == 403
    assert reader.get(f"{BASE}/00000000-0000-0000-0000-000000000000").status_code == 403


def test_the_endpoints_require_a_session_at_all(application):
    anonymous = TestClient(application, headers={})
    assert anonymous.get("/api/devotions").status_code == 401
    assert anonymous.get("/api/devotions/any").status_code == 401
    assert anonymous.get(BASE).status_code == 401


def test_roles_come_from_server_settings_never_from_the_token(application):
    claims = {"role": "admin", "org_role": "org:admin", "public_metadata": {"role": "approver"}}
    forged = TestClient(application, headers=bearer("user_claims_admin", **claims))
    assert forged.get(BASE).status_code == 403


def test_nobody_holds_a_role_by_default():
    settings = Settings(_env_file=None)
    assert settings.editor_clerk_user_ids == [] and settings.approver_clerk_user_ids == []


def test_role_settings_must_be_clerk_user_ids():
    with pytest.raises(ValidationError):
        Settings(editor_clerk_user_ids="admin@example.com", _env_file=None)
    assert Settings(approver_clerk_user_ids="user_a, user_b", _env_file=None).approver_clerk_user_ids == [
        "user_a", "user_b",
    ]


def test_an_editor_cannot_approve_or_publish_and_an_approver_cannot_edit(editor, approver):
    devotion = make_devotion(editor)
    text_row = make_text(editor, devotion)
    url = f"{BASE}/{devotion['id']}/texts/{text_row['id']}/transition"
    move(editor, url, "source_verified")
    move(editor, url, "pending_approval")
    assert editor.post(url, json={"to": "approved"}).status_code == 403
    dev_url = f"{BASE}/{devotion['id']}/transition"
    for step in ("source_verified", "pending_approval"):
        move(editor, dev_url, step)
    move(approver, url, "approved")
    assert editor.post(dev_url, json={"to": "approved"}).status_code == 403
    move(approver, dev_url, "approved")
    assert editor.post(dev_url, json={"to": "published"}).status_code == 403
    assert approver.post(BASE, json={"slug": "y", "title": "T", "overview": "O"}).status_code == 403
    assert approver.patch(f"{BASE}/{devotion['id']}", json={"title": "New"}).status_code == 403
    assert approver.post(
        f"{BASE}/{devotion['id']}/texts", json={"slot": "z", "language": "en", "body": "b"},
    ).status_code == 403


def test_both_roles_can_be_held_by_one_person(application):
    both = as_(application, BOTH)
    devotion = make_devotion(both)
    text_row = make_text(both, devotion)
    approve_text(both, both, devotion, text_row)
    assert publish(both, both, devotion)["status"] == "published"


def test_approval_is_attributed_to_the_approver(editor, approver):
    devotion, text_row = published_with_text(editor, approver)
    stored = editor.get(f"{BASE}/{devotion['id']}").json()
    assert stored["approved_by"] == APPROVER and stored["created_by"] == EDITOR
    assert stored["texts"][0]["entered_by"] == EDITOR
    assert stored["texts"][0]["source_verified_by"] == EDITOR
    assert stored["texts"][0]["approved_by"] == APPROVER


# ---- The workflow ------------------------------------------------------------------------------
def test_a_new_devotion_is_a_hidden_proposal(editor, reader):
    devotion = make_devotion(editor)
    make_text(editor, devotion)
    assert devotion["status"] == "proposed"
    assert reader.get("/api/devotions").json() == []
    missing = reader.get("/api/devotions/never-existed")
    draft = reader.get("/api/devotions/test-devotion")
    assert draft.status_code == missing.status_code == 404
    assert draft.json() == missing.json()      # a reader cannot tell a draft from nothing


@pytest.mark.parametrize("target", ["approved", "published", "pending_approval"])
def test_steps_cannot_be_skipped(editor, approver, target):
    devotion = make_devotion(editor)
    text_row = make_text(editor, devotion)
    assert approver.post(f"{BASE}/{devotion['id']}/transition", json={"to": target}).status_code == 409
    url = f"{BASE}/{devotion['id']}/texts/{text_row['id']}/transition"
    assert approver.post(url, json={"to": target}).status_code in {403, 409}
    assert editor.post(url, json={"to": "published"}).status_code == 409


def test_wording_needs_an_attributable_source_before_it_can_be_verified(editor):
    devotion = make_devotion(editor)
    text_row = editor.post(f"{BASE}/{devotion['id']}/texts", json={
        "slot": "main", "language": "en", "body": "Filler wording",
    }).json()
    assert len(text_row["problems"]) == 3
    url = f"{BASE}/{devotion['id']}/texts/{text_row['id']}/transition"
    refused = editor.post(url, json={"to": "source_verified"})
    assert refused.status_code == 409 and "source" in refused.json()["detail"].lower()
    editor.patch(f"{BASE}/{devotion['id']}/texts/{text_row['id']}", json=SOURCE)
    move(editor, url, "source_verified")


def test_a_translation_needs_a_named_translator(editor):
    devotion = make_devotion(editor)
    text_row = make_text(editor, devotion, is_translation=True)
    url = f"{BASE}/{devotion['id']}/texts/{text_row['id']}/transition"
    refused = editor.post(url, json={"to": "source_verified"})
    assert refused.status_code == 409 and "translator" in refused.json()["detail"].lower()
    editor.patch(f"{BASE}/{devotion['id']}/texts/{text_row['id']}", json={"translator": "T. Filler"})
    move(editor, url, "source_verified")


def test_unknown_licence_status_blocks_verification(editor):
    devotion = make_devotion(editor)
    text_row = make_text(editor, devotion, license_status="unverified")
    url = f"{BASE}/{devotion['id']}/texts/{text_row['id']}/transition"
    assert editor.post(url, json={"to": "source_verified"}).status_code == 409


def test_commentary_must_cite_a_source(editor):
    devotion = make_devotion(editor, background="Background filler")
    url = f"{BASE}/{devotion['id']}/transition"
    assert editor.post(url, json={"to": "source_verified"}).status_code == 409
    editor.patch(f"{BASE}/{devotion['id']}", json={"references": [{"label": "Filler reference"}]})
    move(editor, url, "source_verified")


def test_steps_must_use_texts_that_exist(editor):
    steps = [{"kind": "prayer", "text_slot": "opening"}]
    devotion = make_devotion(editor, steps=steps)
    url = f"{BASE}/{devotion['id']}/transition"
    assert editor.post(url, json={"to": "source_verified"}).status_code == 409
    make_text(editor, devotion, slot="opening")
    move(editor, url, "source_verified")


def test_the_full_path_publishes_exactly_the_approved_wording(editor, approver, reader):
    devotion, text_row = published_with_text(editor, approver)
    listing = reader.get("/api/devotions").json()
    assert [(d["slug"], d["has_text"]) for d in listing] == [("test-devotion", True)]
    detail = reader.get("/api/devotions/test-devotion").json()
    assert detail["texts"][0]["body"] == BODY       # byte for byte: spaces, blank lines, tabs
    assert detail["texts"][0]["source"]["title"] == "A Test Source Book"
    assert detail["texts"][0]["source"]["attribution"] == "Filler attribution line"


def test_readers_never_receive_internal_editorial_fields(editor, approver, reader):
    devotion, _ = published_with_text(editor, approver, license_notes="internal licence note")
    raw = reader.get("/api/devotions/test-devotion").text
    for private in (EDITOR, APPROVER, "approved_hash", "entered_by", "internal licence note"):
        assert private not in raw


@pytest.mark.parametrize("stop_at", [None, "source_verified", "pending_approval"])
def test_wording_that_is_not_approved_is_never_shown(editor, approver, reader, stop_at):
    devotion = make_devotion(editor)
    approved = make_text(editor, devotion, language="la", body="Approved filler wording")
    approve_text(editor, approver, devotion, approved)    # something must be approved to publish at all
    text_row = make_text(editor, devotion)                # English, carrying MARKER, stops short
    url = f"{BASE}/{devotion['id']}/texts/{text_row['id']}/transition"
    steps = {None: [], "source_verified": ["source_verified"],
             "pending_approval": ["source_verified", "pending_approval"]}[stop_at]
    for step in steps:
        move(editor, url, step)
    publish(editor, approver, devotion)        # the devotion itself is approved and published
    page = reader.get("/api/devotions/test-devotion")
    assert page.status_code == 200
    assert [t["language"] for t in page.json()["texts"]] == ["la"]
    assert MARKER not in page.text and MARKER not in reader.get("/api/devotions").text
    assert reader.get("/api/devotions").json()[0]["has_text"] is True


def test_each_language_is_approved_separately(editor, approver, reader):
    devotion = make_devotion(editor)
    english = make_text(editor, devotion, language="en", body="English filler")
    latin = make_text(editor, devotion, language="la", body="Latin filler", is_translation=False)
    approve_text(editor, approver, devotion, english)
    publish(editor, approver, devotion)
    assert [t["language"] for t in reader.get("/api/devotions/test-devotion").json()["texts"]] == ["en"]
    approve_text(editor, approver, devotion, latin)
    languages = [t["language"] for t in reader.get("/api/devotions/test-devotion").json()["texts"]]
    assert sorted(languages) == ["en", "la"]


def test_a_devotion_that_is_approved_but_not_published_is_hidden(editor, approver, reader):
    devotion = make_devotion(editor)
    approve_text(editor, approver, devotion, make_text(editor, devotion))
    url = f"{BASE}/{devotion['id']}/transition"
    for step in ("source_verified", "pending_approval"):
        move(editor, url, step)
    move(approver, url, "approved")
    assert reader.get("/api/devotions/test-devotion").status_code == 404


def test_unpublishing_and_withdrawing_hide_content_again(editor, approver, reader):
    devotion, text_row = published_with_text(editor, approver)
    move(approver, f"{BASE}/{devotion['id']}/transition", "approved")
    assert reader.get("/api/devotions/test-devotion").status_code == 404
    move(approver, f"{BASE}/{devotion['id']}/transition", "published")
    assert reader.get("/api/devotions/test-devotion").json()["texts"]
    url = f"{BASE}/{devotion['id']}/texts/{text_row['id']}/transition"
    assert editor.post(url, json={"to": "proposed"}).status_code == 403   # only an approver may withdraw
    move(approver, url, "proposed")
    assert reader.get("/api/devotions/test-devotion").json()["texts"] == []


# ---- Changing approved content cancels the approval -------------------------------------------
@pytest.mark.parametrize("change", [
    {"body": BODY + "one more line"}, {"attribution": "A different credit"},
    {"source_title": "Another book"}, {"language": "la"}, {"translator": "New Translator"},
    {"license_status": "licensed"},
])
def test_any_change_to_approved_wording_or_its_citation_invalidates_the_approval(
    editor, approver, reader, change,
):
    devotion, text_row = published_with_text(editor, approver)
    edited = editor.patch(f"{BASE}/{devotion['id']}/texts/{text_row['id']}", json=change).json()
    assert edited["status"] == "proposed" and edited["approval_current"] is False
    assert edited["approved_by"] is None and edited["source_verified_by"] is None
    assert reader.get("/api/devotions/test-devotion").json()["texts"] == []
    # It has to earn approval again, from the start.
    url = f"{BASE}/{devotion['id']}/texts/{text_row['id']}/transition"
    assert approver.post(url, json={"to": "approved"}).status_code == 409
    for step in ("source_verified", "pending_approval"):
        move(editor, url, step)
    move(approver, url, "approved")
    assert len(reader.get("/api/devotions/test-devotion").json()["texts"]) == 1


def test_a_save_that_changes_nothing_keeps_the_approval(editor, approver, reader):
    devotion, text_row = published_with_text(editor, approver)
    same = editor.patch(
        f"{BASE}/{devotion['id']}/texts/{text_row['id']}", json={"body": BODY, "position": 5},
    ).json()
    assert same["status"] == "approved" and same["approval_current"] is True
    assert reader.get("/api/devotions/test-devotion").json()["texts"]


def test_editing_text_in_review_sends_it_back_to_the_start(editor):
    devotion = make_devotion(editor)
    text_row = make_text(editor, devotion)
    url = f"{BASE}/{devotion['id']}/texts/{text_row['id']}/transition"
    move(editor, url, "source_verified")
    move(editor, url, "pending_approval")
    edited = editor.patch(f"{BASE}/{devotion['id']}/texts/{text_row['id']}", json={"body": "other"})
    assert edited.json()["status"] == "proposed"


@pytest.mark.parametrize("change", [
    {"overview": "A changed overview"}, {"title": "Another title"}, {"instructions": ["Step one"]},
    {"slug": "another-address"}, {"steps": [{"kind": "instruction", "instruction": "Pause"}]},
])
def test_changing_an_approved_devotion_unpublishes_it(editor, approver, reader, change):
    devotion, _ = published_with_text(editor, approver)
    edited = editor.patch(f"{BASE}/{devotion['id']}", json=change).json()
    assert edited["status"] == "proposed" and edited["published_at"] is None
    assert reader.get("/api/devotions").json() == []


def test_changing_the_wording_does_not_unpublish_the_devotion_but_hides_the_text(
    editor, approver, reader,
):
    devotion, text_row = published_with_text(editor, approver)
    editor.patch(f"{BASE}/{devotion['id']}/texts/{text_row['id']}", json={"body": "changed"})
    page = reader.get("/api/devotions/test-devotion").json()
    assert page["texts"] == [] and page["overview"] == "Overview filler"


# ---- Defence in depth: the fingerprint and the database ---------------------------------------
def test_content_altered_behind_the_applications_back_stops_being_served(
    application, editor, approver, reader,
):
    devotion, text_row = published_with_text(editor, approver)
    with application.state.session_factory.begin() as db:
        db.execute(text("UPDATE prayer_texts SET body = 'tampered filler'"))
    page = reader.get("/api/devotions/test-devotion")
    assert page.status_code == 200 and page.json()["texts"] == []
    assert "tampered" not in page.text
    with application.state.session_factory.begin() as db:
        db.execute(text("UPDATE devotions SET overview = 'tampered overview'"))
    assert reader.get("/api/devotions/test-devotion").status_code == 404
    assert reader.get("/api/devotions").json() == []


def test_the_database_refuses_approval_records_that_are_missing(application):
    with application.state.session_factory() as db:
        db.add(Devotion(slug="x", title="T", overview="O", status="published", created_by="u"))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()
        devotion = Devotion(slug="y", title="T", overview="O", created_by="u")
        db.add(devotion)
        db.flush()
        db.add(PrayerText(
            devotion_id=devotion.id, slot="a", language="en", body="b", status="approved",
            entered_by="u", source_title="s", attribution="a", license_status="public_domain",
        ))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()


@pytest.mark.parametrize("fields", [
    {"source_title": None}, {"attribution": None}, {"license_status": "unverified"},
])
def test_the_database_refuses_verified_wording_without_a_source(application, fields):
    from datetime import UTC, datetime
    with application.state.session_factory() as db:
        devotion = Devotion(slug="z", title="T", overview="O", created_by="u")
        db.add(devotion)
        db.flush()
        values = {"source_title": "s", "attribution": "a", "license_status": "public_domain", **fields}
        db.add(PrayerText(
            devotion_id=devotion.id, slot="a", language="en", body="b", status="source_verified",
            entered_by="u", source_verified_by="u", source_verified_at=datetime.now(UTC), **values,
        ))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()


def test_blank_wording_is_refused_by_the_api_and_the_database(application, editor):
    devotion = make_devotion(editor)
    refused = editor.post(
        f"{BASE}/{devotion['id']}/texts", json={"slot": "a", "language": "en", "body": "  \n "},
    )
    assert refused.status_code == 422                     # spaces are not wording
    with application.state.session_factory() as db:
        db.add(PrayerText(                                 # a proposal may hold no wording...
            devotion_id=UUID(devotion["id"]), slot="a", language="en", body="", entered_by="u",
        ))
        db.flush()
        db.rollback()
        db.add(PrayerText(                                 # ...but nothing past it may
            devotion_id=UUID(devotion["id"]), slot="b", language="en", body=" ", entered_by="u",
            status="source_verified", source_title="s", attribution="a",
            license_status="public_domain", source_verified_by="u",
            source_verified_at=datetime.now(UTC),
        ))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()


# ---- Input rules --------------------------------------------------------------------------------
@pytest.mark.parametrize("slug", ["preview", "Has Capitals", "has_underscore", "-lead", "a" * 81, ""])
def test_addresses_are_restricted(editor, slug):
    body = {"slug": slug, "title": "T", "overview": "O"}
    assert editor.post(BASE, json=body).status_code == 422


def test_an_address_cannot_be_reused(editor):
    make_devotion(editor, "taken")
    duplicate = editor.post(BASE, json={"slug": "taken", "title": "T", "overview": "O"})
    assert duplicate.status_code == 409
    other = make_devotion(editor, "free")
    assert editor.patch(f"{BASE}/{other['id']}", json={"slug": "taken"}).status_code == 409


def test_citation_links_must_be_web_addresses(editor):
    base = {"slug": "links", "title": "T", "overview": "O"}
    bad = editor.post(BASE, json={**base, "references": [{"label": "L", "url": "javascript:alert(1)"}]})
    assert bad.status_code == 422
    ok = editor.post(BASE, json={**base, "references": [{"label": "L", "url": "https://example.org/x"}]})
    assert ok.status_code == 201
    devotion = ok.json()
    refused = editor.post(
        f"{BASE}/{devotion['id']}/texts",
        json={"slot": "a", "language": "en", "body": "b", "source_url": "ftp://example.org"},
    )
    assert refused.status_code == 422


@pytest.mark.parametrize("step", [
    {"kind": "prayer"}, {"kind": "response"}, {"kind": "instruction"},
    {"kind": "instruction", "instruction": "Pause", "text_slot": "a"},
    {"kind": "prayer", "text_slot": "a", "repeat": 0}, {"kind": "prayer", "text_slot": "Bad Slot"},
])
def test_steps_are_validated(editor, step):
    body = {"slug": "steps", "title": "T", "overview": "O", "steps": [step]}
    assert editor.post(BASE, json=body).status_code == 422


def test_a_complex_sequence_round_trips_through_the_reader_api(editor, approver, reader):
    steps = [
        {"kind": "instruction", "instruction": "Begin quietly", "section": "Opening"},
        {"kind": "prayer", "text_slot": "opening", "title": "Opening"},
        {"kind": "prayer", "text_slot": "refrain", "repeat": 10, "section": "Section one"},
        {"kind": "response", "text_slot": "closing"},
    ]
    devotion = make_devotion(
        editor, instructions=["First instruction", "Second instruction"], steps=steps,
        references=[{"label": "Filler reference", "url": "https://example.org"}],
        background="Background filler", significance="Significance filler", category="Filler",
        estimated_minutes=20, subtitle="Subtitle filler",
    )
    texts = [make_text(editor, devotion, slot=s, body=f"{s} filler") for s in ("opening", "refrain")]
    for row in texts:
        approve_text(editor, approver, devotion, row)
    closing = make_text(editor, devotion, slot="closing", body="closing filler")
    approve_text(editor, approver, devotion, closing)
    make_text(editor, devotion, slot="closing", language="la", body="closing latin filler")  # never approved
    publish(editor, approver, devotion)
    detail = reader.get("/api/devotions/test-devotion").json()
    assert [s["kind"] for s in detail["steps"]] == ["instruction", "prayer", "prayer", "response"]
    assert detail["steps"][2]["repeat"] == 10 and detail["steps"][0]["section"] == "Opening"
    assert detail["instructions"] == ["First instruction", "Second instruction"]
    assert {(t["slot"], t["language"]) for t in detail["texts"]} == {
        ("opening", "en"), ("refrain", "en"), ("closing", "en"),
    }                                                                       # not closing/la
    assert detail["references"] == [{"label": "Filler reference", "url": "https://example.org"}]
    assert (detail["category"], detail["estimated_minutes"]) == ("Filler", 20)


# ---- Deleting and the log ----------------------------------------------------------------------
def test_approved_content_must_be_withdrawn_before_it_can_be_deleted(editor, approver):
    devotion, text_row = published_with_text(editor, approver)
    assert editor.delete(f"{BASE}/{devotion['id']}/texts/{text_row['id']}").status_code == 409
    assert editor.delete(f"{BASE}/{devotion['id']}").status_code == 409
    move(approver, f"{BASE}/{devotion['id']}/transition", "proposed")
    move(approver, f"{BASE}/{devotion['id']}/texts/{text_row['id']}/transition", "proposed")
    assert editor.delete(f"{BASE}/{devotion['id']}/texts/{text_row['id']}").status_code == 204
    assert editor.delete(f"{BASE}/{devotion['id']}").status_code == 204
    assert editor.get(f"{BASE}/{devotion['id']}").status_code == 404


def test_the_editorial_log_records_who_did_what_but_never_the_wording(editor, approver):
    devotion, text_row = published_with_text(editor, approver)
    editor.patch(f"{BASE}/{devotion['id']}/texts/{text_row['id']}", json={"body": "log filler"})
    events = editor.get(f"{BASE}/{devotion['id']}/events")
    assert events.status_code == 200
    rows = events.json()
    assert {(e["action"], e["actor"]) for e in rows} >= {
        ("created", EDITOR), ("text_created", EDITOR), ("transition", EDITOR),
        ("transition", APPROVER), ("text_updated", EDITOR),
    }
    assert MARKER not in events.text and "log filler" not in events.text
    updated = next(e for e in rows if e["action"] == "text_updated")
    assert updated["note"] == "body" and updated["to_status"] == "proposed"


def test_a_missing_devotion_or_text_is_a_404(editor):
    missing = "00000000-0000-0000-0000-000000000009"
    assert editor.get(f"{BASE}/{missing}").status_code == 404
    devotion = make_devotion(editor)
    assert editor.patch(
        f"{BASE}/{devotion['id']}/texts/{missing}", json={"body": "x"},
    ).status_code == 404


def test_one_version_per_language_per_text(editor):
    devotion = make_devotion(editor)
    make_text(editor, devotion, slot="main", language="en")
    duplicate = editor.post(
        f"{BASE}/{devotion['id']}/texts", json={"slot": "main", "language": "en", "body": "b"},
    )
    assert duplicate.status_code == 409
    other = make_text(editor, devotion, slot="main", language="la")
    assert editor.patch(
        f"{BASE}/{devotion['id']}/texts/{other['id']}", json={"language": "en"},
    ).status_code == 409


# ---- Reader bookmarks ----------------------------------------------------------------------------
def test_bookmarks_belong_to_one_reader_and_record_nothing_else(application, editor, approver, reader):
    published_with_text(editor, approver)
    other = as_(application, OTHER_READER)
    assert reader.put("/api/devotions/test-devotion/bookmark").json() == {"bookmarked": True}
    assert reader.put("/api/devotions/test-devotion/bookmark").json() == {"bookmarked": True}
    assert reader.get("/api/devotions").json()[0]["bookmarked"] is True
    assert reader.get("/api/devotions/test-devotion").json()["bookmarked"] is True
    assert other.get("/api/devotions").json()[0]["bookmarked"] is False
    assert reader.delete("/api/devotions/test-devotion/bookmark").json() == {"bookmarked": False}
    assert reader.get("/api/devotions").json()[0]["bookmarked"] is False


def test_only_published_devotions_can_be_bookmarked(editor, reader):
    make_devotion(editor)
    assert reader.put("/api/devotions/test-devotion/bookmark").status_code == 404


def test_bookmarks_hold_no_dates_counts_or_history():
    from app.models import DevotionBookmark
    assert {c.name for c in DevotionBookmark.__table__.columns} == {"user_id", "devotion_id"}
