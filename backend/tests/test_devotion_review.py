# ruff: noqa: E501, F811
"""Devotions, editorial review: rights and withheld wording, independent languages, publication
prerequisites, reusing a prayer from another devotion, recorded decisions, and the private preview.
All wording below is neutral test filler, never a real prayer."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from test_devotions import (  # noqa: F401  (fixtures and helpers shared with the main devotion tests)
    APPROVER,
    BASE,
    BOTH,
    EDITOR,
    MARKER,
    OTHER_READER,
    READER,
    SOURCE,
    approve_text,
    approver,
    as_,
    editor,
    make_devotion,
    make_text,
    move,
    publish,
    reader,
    roles,
)

LATIN = "Latin filler wording"
ENGLISH = "English filler wording"


def text_url(devotion, row):
    return f"{BASE}/{devotion['id']}/texts/{row['id']}/transition"


def detail(client, devotion):
    return client.get(f"{BASE}/{devotion['id']}").json()


# ---- Wording withheld, rights not cleared -------------------------------------------------------
RESTRICTED = {
    "source_title": "A Test Source Book", "source_authority": "A Test Authority",
    "source_edition": "2nd test edition", "source_date": "2005", "source_url": "https://example.org/source",
    "attribution": "Filler attribution line", "license_status": "restricted",
    "license_notes": "The owner's terms do not clearly permit republishing",
}


def withheld(editor, devotion, slot="main", language="la", **extra):
    """A text that is only a citation and link: the wording is withheld."""
    response = editor.post(f"{BASE}/{devotion['id']}/texts", json={"slot": slot, "language": language, "body": "", **RESTRICTED, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def test_a_citation_can_be_kept_with_no_wording_when_rights_are_not_cleared(editor):
    devotion = make_devotion(editor)
    row = withheld(editor, devotion)
    assert row["body"] == "" and row["has_body"] is False and row["rights_cleared"] is False
    assert (row["source_authority"], row["source_date"], row["source_url"]) == ("A Test Authority", "2005", "https://example.org/source")
    assert row["status"] == "proposed"
    assert any("No wording is held" in problem for problem in row["problems"])
    assert any("rights are not cleared" in problem.lower() for problem in row["problems"])


@pytest.mark.parametrize("fields, fragment", [
    ({"license_status": "restricted"}, "rights are not cleared"),
    ({"license_status": "unverified"}, "public domain, licensed or permitted"),
])
def test_wording_whose_rights_are_not_cleared_cannot_be_verified(editor, fields, fragment):
    devotion = make_devotion(editor)
    row = make_text(editor, devotion, body=ENGLISH, **fields)
    refused = editor.post(text_url(devotion, row), json={"to": "source_verified"})
    assert refused.status_code == 409
    assert fragment.lower() in refused.json()["detail"].lower()


def test_a_text_with_no_wording_cannot_be_verified_even_with_cleared_rights(editor):
    devotion = make_devotion(editor)
    row = withheld(editor, devotion, license_status="public_domain")
    refused = editor.post(text_url(devotion, row), json={"to": "source_verified"})
    assert refused.status_code == 409 and "No wording is held" in refused.json()["detail"]


def test_withheld_wording_never_reaches_a_reader_even_if_everything_else_is_published(editor, approver, reader):
    devotion = make_devotion(editor)
    approve_text(editor, approver, devotion, make_text(editor, devotion, language="en", body=ENGLISH))
    withheld(editor, devotion, language="la")
    publish(editor, approver, devotion)
    page = reader.get("/api/devotions/test-devotion").json()
    assert [t["language"] for t in page["texts"]] == ["en"]
    assert "A Test Authority" not in reader.get("/api/devotions/test-devotion").text   # the withheld citation is editorial


def test_once_the_wording_is_supplied_and_rights_cleared_it_can_proceed(editor, approver, reader):
    devotion = make_devotion(editor)
    row = withheld(editor, devotion, language="en")
    updated = editor.patch(f"{BASE}/{devotion['id']}/texts/{row['id']}", json={"body": ENGLISH, "license_status": "public_domain"}).json()
    assert updated["has_body"] and updated["rights_cleared"] and updated["problems"] == []
    approve_text(editor, approver, devotion, updated)
    assert detail(editor, devotion)["texts"][0]["status"] == "approved"


def test_the_database_refuses_to_advance_restricted_or_wordless_texts(application, editor):
    from uuid import UUID

    from sqlalchemy.exc import IntegrityError

    from app.models import PrayerText
    devotion = make_devotion(editor)
    for fields in ({"license_status": "restricted", "body": "wording"}, {"license_status": "public_domain", "body": ""}):
        with application.state.session_factory() as db:
            db.add(PrayerText(
                devotion_id=UUID(devotion["id"]), slot="x", language="en", status="source_verified", entered_by="u",
                source_title="s", attribution="a", source_verified_by="u", source_verified_at=datetime.now(UTC), **fields,
            ))
            with pytest.raises(IntegrityError):
                db.flush()
            db.rollback()


# ---- Source metadata is part of what is approved --------------------------------------------------
@pytest.mark.parametrize("change", [
    {"source_authority": "Another authority"}, {"source_date": "1999"}, {"source_edition": "3rd"},
    {"source_url": "https://example.org/other"}, {"license_notes": "New terms"},
    {"source_retrieved_at": "2026-01-02T03:04:05Z"},
])
def test_changing_any_source_metadata_cancels_the_approval(editor, approver, reader, change):
    devotion = make_devotion(editor)
    row = make_text(editor, devotion, body=ENGLISH, source_retrieved_at="2026-01-01T00:00:00Z")
    approve_text(editor, approver, devotion, row)
    publish(editor, approver, devotion)
    assert reader.get("/api/devotions/test-devotion").json()["texts"]
    edited = editor.patch(f"{BASE}/{devotion['id']}/texts/{row['id']}", json=change).json()
    assert edited["status"] == "proposed" and edited["approval_current"] is False
    assert reader.get("/api/devotions/test-devotion").json()["texts"] == []


# ---- English and Latin are independent -----------------------------------------------------------
def test_a_devotion_can_be_published_with_english_alone_and_latin_added_later(editor, approver, reader):
    devotion = make_devotion(editor)
    english = make_text(editor, devotion, language="en", body=ENGLISH)
    latin = make_text(editor, devotion, language="la", body=LATIN)
    approve_text(editor, approver, devotion, english)
    publish(editor, approver, devotion)
    page = reader.get("/api/devotions/test-devotion")
    assert [t["language"] for t in page.json()["texts"]] == ["en"] and LATIN not in page.text      # Latin is only pending
    move(editor, text_url(devotion, latin), "source_verified")
    move(editor, text_url(devotion, latin), "pending_approval")
    assert LATIN not in reader.get("/api/devotions/test-devotion").text
    move(approver, text_url(devotion, latin), "approved")
    assert sorted(t["language"] for t in reader.get("/api/devotions/test-devotion").json()["texts"]) == ["en", "la"]


def test_rejecting_one_language_leaves_the_other_untouched(editor, approver, reader):
    devotion = make_devotion(editor)
    english = make_text(editor, devotion, language="en", body=ENGLISH)
    latin = make_text(editor, devotion, language="la", body=LATIN)
    approve_text(editor, approver, devotion, english)
    approve_text(editor, approver, devotion, latin)
    publish(editor, approver, devotion)
    move(approver, text_url(devotion, latin), "proposed")
    assert [t["language"] for t in reader.get("/api/devotions/test-devotion").json()["texts"]] == ["en"]
    states = {t["language"]: t["status"] for t in detail(editor, devotion)["texts"]}
    assert states == {"en": "approved", "la": "proposed"}


def test_the_review_queue_summarises_each_language_separately(editor, approver):
    devotion = make_devotion(editor, category="Our Lady")
    approve_text(editor, approver, devotion, make_text(editor, devotion, language="en", body=ENGLISH))
    withheld(editor, devotion, language="la")
    (brief,) = editor.get(BASE).json()
    assert (brief["category"], brief["status"], brief["texts_approved"], brief["texts_total"]) == ("Our Lady", "proposed", 1, 2)
    by_language = {t["language"]: t for t in brief["texts"]}
    assert by_language["en"] == {"slot": "main", "language": "en", "status": "approved", "license_status": "public_domain", "has_body": True, "source_verified": True}
    assert by_language["la"]["has_body"] is False and by_language["la"]["license_status"] == "restricted" and by_language["la"]["source_verified"] is False


# ---- Publication prerequisites -----------------------------------------------------------------
def test_a_devotion_cannot_be_published_with_no_approved_prayer_text(editor, approver):
    devotion = make_devotion(editor)
    make_text(editor, devotion, body=ENGLISH)                         # proposed only
    url = f"{BASE}/{devotion['id']}/transition"
    for step in ("source_verified", "pending_approval"):
        move(editor, url, step)
    move(approver, url, "approved")
    refused = approver.post(url, json={"to": "published"})
    assert refused.status_code == 409 and "No prayer text is approved yet" in refused.json()["detail"]
    assert detail(editor, devotion)["publication_problems"] == ["No prayer text is approved yet: approve at least one (English or Latin)"]


def test_the_editorial_view_lists_exactly_what_still_blocks_publication(editor, approver):
    devotion = make_devotion(editor, steps=[{"kind": "prayer", "text_slot": "main"}])
    view = detail(editor, devotion)
    assert "The devotion itself has not been approved yet" in view["publication_problems"]
    assert any(problem.startswith("Step 1 needs an approved text") for problem in view["publication_problems"])
    approve_text(editor, approver, devotion, make_text(editor, devotion, body=ENGLISH))
    assert "The devotion itself has not been approved yet" in detail(editor, devotion)["publication_problems"]
    assert not any("Step 1" in problem for problem in detail(editor, devotion)["publication_problems"])


def test_every_prayer_step_needs_approved_wording_before_publication(editor, approver):
    devotion = make_devotion(editor, steps=[{"kind": "prayer", "text_slot": "one"}, {"kind": "prayer", "text_slot": "two"}])
    approve_text(editor, approver, devotion, make_text(editor, devotion, slot="one", body=ENGLISH))
    make_text(editor, devotion, slot="two", body=LATIN)               # never approved
    url = f"{BASE}/{devotion['id']}/transition"
    for step in ("source_verified", "pending_approval"):
        move(editor, url, step)
    move(approver, url, "approved")
    refused = approver.post(url, json={"to": "published"})
    assert refused.status_code == 409 and "Step 2 needs an approved text for test-devotion/two" in refused.json()["detail"]


# ---- Reusing a prayer kept in another devotion --------------------------------------------------
def rosary_like(editor, slug="outer", reuse="inner", slot="main"):
    return make_devotion(editor, slug, steps=[
        {"kind": "instruction", "instruction": "Begin", "section": "Opening"},
        {"kind": "prayer", "text_slot": slot, "devotion_slug": reuse, "title": "Reused prayer", "section": "Opening"},
    ])


def test_a_step_can_reuse_a_prayer_from_another_devotion_without_copying_it(editor, approver, reader):
    inner = make_devotion(editor, "inner")
    approve_text(editor, approver, inner, make_text(editor, inner, body=ENGLISH))
    publish(editor, approver, inner)
    outer = rosary_like(editor)
    approve_text(editor, approver, outer, make_text(editor, outer, slot="own", body="Own filler wording"))
    outer_url = f"{BASE}/{outer['id']}/transition"
    for step in ("source_verified", "pending_approval"):
        move(editor, outer_url, step)
    move(approver, outer_url, "approved")
    move(approver, outer_url, "published")
    page = reader.get("/api/devotions/outer").json()
    reused = [t for t in page["texts"] if t["devotion_slug"] == "inner"]
    assert [(t["slot"], t["body"]) for t in reused] == [("main", ENGLISH)]      # served from the one stored copy
    assert reader.get("/api/devotions").json()[0]["has_text"] is True


def test_a_reused_prayer_appears_only_while_its_own_devotion_is_published_and_approved(editor, approver, reader):
    inner = make_devotion(editor, "inner")
    row = make_text(editor, inner, body=ENGLISH)
    approve_text(editor, approver, inner, row)
    publish(editor, approver, inner)
    outer = rosary_like(editor)
    approve_text(editor, approver, outer, make_text(editor, outer, slot="own", body="Own filler wording"))
    url = f"{BASE}/{outer['id']}/transition"
    for step in ("source_verified", "pending_approval"):
        move(editor, url, step)
    move(approver, url, "approved")
    move(approver, url, "published")
    assert any(t["devotion_slug"] == "inner" for t in reader.get("/api/devotions/outer").json()["texts"])
    move(approver, f"{BASE}/{inner['id']}/transition", "approved")                  # unpublish the source devotion
    assert not any(t["devotion_slug"] == "inner" for t in reader.get("/api/devotions/outer").json()["texts"])
    move(approver, f"{BASE}/{inner['id']}/transition", "published")
    move(approver, text_url(inner, row), "proposed")                                # withdraw the text itself
    assert not any(t["devotion_slug"] == "inner" for t in reader.get("/api/devotions/outer").json()["texts"])


def test_a_devotion_cannot_be_published_before_the_devotions_it_reuses(editor, approver):
    inner = make_devotion(editor, "inner")
    approve_text(editor, approver, inner, make_text(editor, inner, body=ENGLISH))         # approved text, devotion unpublished
    outer = rosary_like(editor)
    outer_url = f"{BASE}/{outer['id']}/transition"
    for step in ("source_verified", "pending_approval"):
        move(editor, outer_url, step)
    move(approver, outer_url, "approved")
    refused = approver.post(outer_url, json={"to": "published"})
    assert refused.status_code == 409 and "reuses inner/main, but that devotion is not published yet" in refused.json()["detail"]


def test_a_reference_to_a_missing_devotion_or_prayer_blocks_verification(editor):
    missing_devotion = rosary_like(editor, "outer-a", reuse="nowhere")
    refused = editor.post(f"{BASE}/{missing_devotion['id']}/transition", json={"to": "source_verified"})
    assert refused.status_code == 409 and "does not exist: nowhere" in refused.json()["detail"]
    make_devotion(editor, "inner")
    missing_slot = rosary_like(editor, "outer-b", reuse="inner", slot="absent")
    refused = editor.post(f"{BASE}/{missing_slot['id']}/transition", json={"to": "source_verified"})
    assert refused.status_code == 409 and "inner/absent" in refused.json()["detail"]


def test_a_reused_prayer_does_not_leak_into_a_devotion_that_does_not_use_it(editor, approver, reader):
    inner = make_devotion(editor, "inner")
    approve_text(editor, approver, inner, make_text(editor, inner, body=ENGLISH))
    publish(editor, approver, inner)
    plain = make_devotion(editor, "plain")
    approve_text(editor, approver, plain, make_text(editor, plain, body="Plain filler wording"))
    publish(editor, approver, plain)
    assert [t["devotion_slug"] for t in reader.get("/api/devotions/plain").json()["texts"]] == ["plain"]


def test_grouped_steps_round_trip(editor, approver, reader):
    steps = [
        {"kind": "instruction", "instruction": "Begin"},
        {"kind": "prayer", "text_slot": "main", "title": "First", "section": "Set A: first", "group": "Set A"},
        {"kind": "prayer", "text_slot": "main", "title": "Second", "section": "Set B: first", "group": "Set B"},
    ]
    devotion = make_devotion(editor, steps=steps, choice_label="Mysteries")
    approve_text(editor, approver, devotion, make_text(editor, devotion, body=ENGLISH))
    publish(editor, approver, devotion)
    page = reader.get("/api/devotions/test-devotion").json()
    assert page["choice_label"] == "Mysteries"
    assert [s["group"] for s in page["steps"]] == [None, "Set A", "Set B"]
    changed = editor.patch(f"{BASE}/{devotion['id']}", json={"choice_label": "Sets"}).json()
    assert changed["status"] == "proposed"                              # the label is approved content too


# ---- Recorded decisions --------------------------------------------------------------------------
def test_returning_for_research_and_rejecting_need_a_reason_and_are_recorded(editor, approver):
    devotion = make_devotion(editor)
    row = make_text(editor, devotion, body=ENGLISH)
    url = text_url(devotion, row)
    move(editor, url, "source_verified")
    assert editor.post(url, json={"to": "proposed", "decision": "return_for_research"}).status_code == 422
    returned = editor.post(url, json={"to": "proposed", "decision": "return_for_research", "note": "Check the edition"})
    assert returned.status_code == 200
    body = returned.json()
    assert body["status"] == "proposed" and body["source_verified_by"] is None
    assert (body["last_event"]["action"], body["last_event"]["note"], body["last_event"]["actor"]) == ("return_for_research", "Check the edition", EDITOR)


def test_a_proposed_text_can_be_rejected_and_stays_proposed_with_the_reason_on_record(editor, approver):
    devotion = make_devotion(editor)
    row = make_text(editor, devotion, body=ENGLISH)
    rejected = editor.post(text_url(devotion, row), json={"to": "proposed", "decision": "reject_text", "note": "Not the right edition"})
    assert rejected.status_code == 200 and rejected.json()["status"] == "proposed"
    assert rejected.json()["last_event"]["action"] == "reject_text"
    events = editor.get(f"{BASE}/{devotion['id']}/events").json()
    assert ("reject_text", "Not the right edition") in [(e["action"], e["note"]) for e in events]


def test_only_an_approver_can_reject_what_was_submitted_for_approval(editor, approver):
    devotion = make_devotion(editor)
    row = make_text(editor, devotion, body=ENGLISH)
    url = text_url(devotion, row)
    move(editor, url, "source_verified")
    move(editor, url, "pending_approval")
    assert editor.post(url, json={"to": "proposed", "decision": "reject_approval", "note": "No"}).status_code == 403
    done = approver.post(url, json={"to": "proposed", "decision": "reject_approval", "note": "Wording differs from the source"})
    assert done.status_code == 200 and done.json()["status"] == "proposed" and done.json()["last_event"]["actor"] == APPROVER


def test_a_decision_only_applies_to_the_moves_it_names(editor, approver):
    devotion = make_devotion(editor)
    row = make_text(editor, devotion, body=ENGLISH)
    url = text_url(devotion, row)
    for decision, to in (("withdraw", "proposed"), ("reject_approval", "proposed"), ("return_for_research", "proposed"), ("reject_text", "source_verified")):
        assert editor.post(url, json={"to": to, "decision": decision, "note": "why"}).status_code == 409
    approve_text(editor, approver, devotion, row)
    withdrawn = approver.post(url, json={"to": "proposed", "decision": "withdraw", "note": "Found an error"})
    assert withdrawn.status_code == 200 and withdrawn.json()["last_event"]["action"] == "withdraw"


def test_an_editor_cannot_withdraw_an_approval(editor, approver):
    devotion = make_devotion(editor)
    row = make_text(editor, devotion, body=ENGLISH)
    approve_text(editor, approver, devotion, row)
    assert editor.post(text_url(devotion, row), json={"to": "proposed", "decision": "withdraw", "note": "x"}).status_code == 403


def test_the_log_records_decisions_but_never_the_wording(editor, approver):
    devotion = make_devotion(editor)
    row = make_text(editor, devotion, body=f"{MARKER} wording")
    editor.post(text_url(devotion, row), json={"to": "proposed", "decision": "reject_text", "note": "Not suitable"})
    assert MARKER not in editor.get(f"{BASE}/{devotion['id']}/events").text
    assert MARKER not in editor.get(BASE).text      # the queue carries statuses, not wording


# ---- The private preview -------------------------------------------------------------------------
def test_the_preview_shows_unapproved_texts_marked_as_such_to_editors_only(application, editor, approver, reader):
    devotion = make_devotion(editor)
    approved = make_text(editor, devotion, language="en", body=ENGLISH)
    make_text(editor, devotion, language="la", body=LATIN)            # a proposal
    approve_text(editor, approver, devotion, approved)
    preview = editor.get(f"{BASE}/{devotion['id']}/preview")
    assert preview.status_code == 200
    body = preview.json()
    assert body["devotion_status"] == "proposed"
    by_language = {t["language"]: t for t in body["texts"]}
    assert (by_language["en"]["status"], by_language["en"]["approval_current"], by_language["en"]["publicly_visible"]) == ("approved", True, False)   # approved, but the devotion is not published
    assert (by_language["la"]["body"], by_language["la"]["status"], by_language["la"]["publicly_visible"]) == (LATIN, "proposed", False)
    assert reader.get(f"{BASE}/{devotion['id']}/preview").status_code == 403
    assert TestClient(application, headers={}).get(f"{BASE}/{devotion['id']}/preview").status_code == 401
    assert reader.get("/api/devotions/test-devotion").status_code == 404           # a preview does not publish anything


def test_the_preview_marks_what_a_reader_would_see_once_published(editor, approver, reader):
    devotion = make_devotion(editor)
    approve_text(editor, approver, devotion, make_text(editor, devotion, language="en", body=ENGLISH))
    make_text(editor, devotion, language="la", body=LATIN)
    publish(editor, approver, devotion)
    visible = {t["language"]: t["publicly_visible"] for t in editor.get(f"{BASE}/{devotion['id']}/preview").json()["texts"]}
    assert visible == {"en": True, "la": False}
    assert [t["language"] for t in reader.get("/api/devotions/test-devotion").json()["texts"]] == ["en"]


def test_the_preview_includes_reused_prayers_with_their_own_status(editor, approver):
    inner = make_devotion(editor, "inner")
    make_text(editor, inner, body=ENGLISH)                              # unapproved, in an unpublished devotion
    outer = rosary_like(editor)
    texts = editor.get(f"{BASE}/{outer['id']}/preview").json()["texts"]
    assert [(t["devotion_slug"], t["slot"], t["publicly_visible"]) for t in texts] == [("inner", "main", False)]


# ---- Who has which role --------------------------------------------------------------------------
def test_a_person_can_see_which_editorial_roles_they_hold(application, editor, approver, reader):
    assert reader.get("/api/editorial-access").json() == {"is_editor": False, "is_approver": False}
    assert editor.get("/api/editorial-access").json() == {"is_editor": True, "is_approver": False}
    assert approver.get("/api/editorial-access").json() == {"is_editor": False, "is_approver": True}
    assert as_(application, BOTH).get("/api/editorial-access").json() == {"is_editor": True, "is_approver": True}
    assert TestClient(application, headers={}).get("/api/editorial-access").status_code == 401


def test_the_roles_endpoint_grants_nothing(reader):
    assert reader.get("/api/editorial/devotions").status_code == 403
    assert reader.post("/api/editorial-access").status_code == 405


def test_ordinary_readers_cannot_reach_any_editorial_endpoint(application, editor):
    devotion = make_devotion(editor)
    other = as_(application, OTHER_READER)
    for method, path, body in (
        ("get", BASE, None), ("get", f"{BASE}/{devotion['id']}", None), ("get", f"{BASE}/{devotion['id']}/preview", None),
        ("get", f"{BASE}/{devotion['id']}/events", None),
        ("post", f"{BASE}/{devotion['id']}/transition", {"to": "source_verified"}),
        ("post", f"{BASE}/{devotion['id']}/texts", {"slot": "a", "language": "en", "body": ""}),
    ):
        response = getattr(other, method)(path, **({"json": body} if body else {}))
        assert response.status_code == 403, (method, path)


def test_nothing_in_the_reader_api_exposes_unpublished_texts_or_citations(editor, approver, reader):
    devotion = make_devotion(editor)
    make_text(editor, devotion, language="en", body=f"{MARKER} draft", **{"source_authority": "Secret Authority"})
    withheld(editor, devotion, language="la")
    for path in ("/api/devotions", "/api/devotions/test-devotion"):
        text = reader.get(path).text
        assert MARKER not in text and "Secret Authority" not in text and "A Test Authority" not in text


def test_an_optional_custom_never_blocks_publication_and_is_flagged(editor, approver, reader):
    steps = [
        {"kind": "prayer", "text_slot": "core"},
        {"kind": "prayer", "text_slot": "custom", "optional": True, "title": "A traditional custom"},
    ]
    devotion = make_devotion(editor, steps=steps)
    approve_text(editor, approver, devotion, make_text(editor, devotion, slot="core", body=ENGLISH))   # no text at all for the custom
    publish(editor, approver, devotion)
    page = reader.get("/api/devotions/test-devotion").json()
    assert [(s["text_slot"], s["optional"]) for s in page["steps"]] == [("core", False), ("custom", True)]
    assert [t["slot"] for t in page["texts"]] == ["core"]


def test_a_core_step_still_blocks_publication_while_an_optional_one_does_not(editor, approver):
    devotion = make_devotion(editor, steps=[{"kind": "prayer", "text_slot": "core"}, {"kind": "prayer", "text_slot": "custom", "optional": True}])
    problems = detail(editor, devotion)["problems"]
    assert any("core" in problem for problem in problems) and not any("custom" in problem for problem in problems)


def test_publication_problems_name_each_unmet_prayer_once_however_many_steps_use_it(editor):
    steps = [{"kind": "prayer", "text_slot": "main", "devotion_slug": "inner"} for _ in range(30)]
    steps += [{"kind": "prayer", "text_slot": "one"}, {"kind": "prayer", "text_slot": "one"}, {"kind": "prayer", "text_slot": "two"}]
    make_devotion(editor, "inner")
    devotion = make_devotion(editor, steps=steps)
    problems = detail(editor, devotion)["publication_problems"]
    assert "30 steps (from step 1) reuse inner/main, but that devotion is not published yet" in problems
    assert "Steps 31 and 32 need an approved text for test-devotion/one" in problems
    assert "Step 33 needs an approved text for test-devotion/two" in problems
    assert sum("inner/main" in problem for problem in problems) == 1
