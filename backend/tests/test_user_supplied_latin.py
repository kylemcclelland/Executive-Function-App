# ruff: noqa: E501, F811
"""The user-supplied Latin prayers: verbatim import, provenance, independence from English, and no public exposure."""

import hashlib
import json
import sys
from pathlib import Path

import pytest
from sqlalchemy import select
from test_devotions import (  # noqa: F401
    BASE,
    approve_text,
    approver,
    editor,
    make_devotion,
    make_text,
    move,
    reader,
    roles,
)

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "seed_data"))

import seed_devotion_drafts as seed  # noqa: E402

from app.models import Devotion, PrayerText  # noqa: E402
from app.services.devotions import has_body  # noqa: E402

DATA = json.loads((SCRIPTS / "seed_data" / "user_supplied_latin.json").read_text(encoding="utf-8"))
ORIGINAL = Path("C:/Users/uvaga/Downloads/latin_prayers_file.txt")
FILE_SHA = "0e9258a9fff356bef4ed34438c8716cad03ce1c5cc08cd54f0de6f82dd777a8c"
MATCH = {"Pater Noster (Our Father)": "our-father", "Ave Maria (Hail Mary)": "hail-mary", "Apostle's Creed": "apostles-creed", "Glory Be": "glory-be", "Angelus": "the-angelus", "Regina Caeli": "regina-caeli"}


@pytest.fixture
def run(application, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", application.state.settings.database_url)

    def go(*flags):
        code = seed.main(list(flags))
        return code, capsys.readouterr().out
    return go


def latin(application):
    with application.state.session_factory() as db:
        slugs = {d.id: d.slug for d in db.scalars(select(Devotion))}
        return {slugs[t.devotion_id]: t for t in db.scalars(select(PrayerText).where(PrayerText.language == "la", PrayerText.slot == "main"))}


# ---- Import integrity, checked independently of the importer -------------------------------------------------
def test_the_six_prayers_in_the_file_were_found_and_matched_to_the_right_devotions():
    assert {item["heading_in_file"]: item["devotion_slug"] for item in DATA["texts"]} == MATCH
    assert DATA["provenance"] == "User-supplied Latin text" and DATA["filename"] == "latin_prayers_file.txt" and DATA["file_sha256"] == FILE_SHA


@pytest.mark.skipif(not ORIGINAL.exists(), reason="the original file is not on this machine")
def test_every_imported_text_matches_the_original_file_exactly_and_nothing_else_was_taken():
    raw = ORIGINAL.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FILE_SHA                      # the file is still the one that was imported
    text = raw.decode("utf-8")
    leftover = text
    for item in DATA["texts"]:
        assert text.count(item["body"]) == 1, item["heading_in_file"]       # present exactly once, byte for byte
        assert hashlib.sha256(item["body"].encode("utf-8")).hexdigest() == item["body_sha256"]
        leftover = leftover.replace(item["body"], "")
    # Removing every imported body leaves only the headings and blank lines: no wording was dropped or added.
    assert sorted(line.strip() for line in leftover.split("\r\n") if line.strip()) == sorted(MATCH)


def test_bodies_keep_what_the_file_has_including_the_oddities_that_were_not_corrected():
    by_slug = {item["devotion_slug"]: item["body"] for item in DATA["texts"]}
    assert "\r\n" in by_slug["our-father"] and "\n" not in by_slug["our-father"].replace("\r\n", "")   # CRLF kept
    assert "mulieri\u00adbus" in by_slug["hail-mary"]                                                   # the soft hyphen is still there
    assert "caelos,sedet" in by_slug["apostles-creed"] and "communionem,remissionem" in by_slug["apostles-creed"]
    assert "Jesus" in by_slug["hail-mary"] and "Iesus" in by_slug["the-angelus"]                        # spelling is not harmonised
    assert by_slug["our-father"].endswith("Amen ")                                                      # trailing space kept
    assert by_slug["the-angelus"].startswith("V. Angelus Domini") and by_slug["regina-caeli"].startswith("V. Regina caeli")


def test_the_unusual_characters_are_listed_as_observations_for_the_reviewer():
    notes = {item["devotion_slug"]: item["observations"] for item in DATA["texts"]}
    assert any("U+00AD" in note and "SOFT HYPHEN" in note for note in notes["hail-mary"])
    assert any("caelos,sedet" in note for note in notes["apostles-creed"])
    assert notes["glory-be"] == [] and notes["the-angelus"] == [] and notes["regina-caeli"] == []


def test_the_importer_refuses_a_file_it_cannot_slice_safely(tmp_path):
    import import_latin_prayers as importer
    mixed = tmp_path / "mixed.txt"
    mixed.write_bytes(b"Glory Be\r\nGloria\nPatri\r\n")
    with pytest.raises(SystemExit):
        importer.parse(mixed.read_bytes())
    partial = tmp_path / "partial.txt"
    partial.write_bytes(b"Glory Be\r\n\r\nGloria Patri\r\n")
    with pytest.raises(SystemExit):
        importer.parse(partial.read_bytes())


# ---- What seeding records ------------------------------------------------------------------------------------
def test_each_supplied_text_is_recorded_with_its_provenance_and_is_unverified_and_unapproved(application, run):
    assert run("--execute")[0] == 0
    import latin_normalization
    normalized = {slug: r["normalized"] for slug, r in latin_normalization.apply_all(DATA).items()}
    texts = latin(application)
    for slug in ("our-father", "hail-mary", "apostles-creed", "glory-be", "the-angelus", "regina-caeli"):
        row = texts[slug]
        item = next(i for i in DATA["texts"] if i["devotion_slug"] == slug)
        assert row.body == normalized[slug]                                          # the authorized normalization of the transcription
        assert "Iesus" not in row.body and "\r" not in row.body and "­" not in row.body   # the authorized corrections are in the stored text
        assert row.body != item["body"]                                                        # it is the normalized version, not the verbatim original
        assert (row.source_title, row.license_status, row.status) == ("User-supplied Latin text", "unverified", "proposed")
        assert row.source_verified_by is None and row.approved_by is None and row.approved_hash is None
        assert row.source_url is None and row.source_date is None and row.translator is None and row.is_translation is False
        assert "latin_prayers_file.txt" in row.source_edition and "latin_prayers_file.txt" in row.attribution
        assert FILE_SHA in row.license_notes and item["heading_in_file"] in row.license_notes and item["body_sha256"] in row.license_notes   # the original's hash is kept
        assert "contains no source reference, edition, translator or rights information" in row.license_notes


def test_the_supplied_texts_replace_the_earlier_citations_and_say_so(application, run):
    run("--execute")
    texts = latin(application)
    for slug in ("our-father", "hail-mary", "apostles-creed", "glory-be", "the-angelus"):
        assert "Replaces the previously cited source record" in texts[slug].license_notes
    assert "Replaces" not in texts["regina-caeli"].license_notes                       # nothing earlier existed for it


def test_prayers_not_in_the_file_keep_their_earlier_records(application, run):
    run("--execute")
    texts = latin(application)
    assert (texts["sign-of-the-cross"].source_title.startswith("Our Monthly Devotions"), has_body(texts["sign-of-the-cross"])) == (True, True)
    assert not has_body(texts["act-of-contrition"]) and texts["act-of-contrition"].license_status == "restricted"


def test_regina_caeli_is_dev_007_under_our_lady_with_latin_only(application, run, editor):
    run("--execute")
    brief = next(d for d in editor.get(BASE).json() if d["slug"] == "regina-caeli")
    assert (brief["category"], brief["status"]) == ("Our Lady", "proposed")
    assert [(t["language"], t["status"], t["license_status"], t["has_body"]) for t in brief["texts"]] == [("la", "proposed", "unverified", True)]
    detail = editor.get(f"{BASE}/{brief['id']}").json()
    assert not any(t["language"] == "en" for t in detail["texts"])                   # English is unavailable, not generated
    assert detail["prose_origin"] == "ai_draft"
    seeded = next(d for d in seed.load_drafts() if d["slug"] == "regina-caeli")
    assert seeded["code"] == "DEV-007" and seeded["category"] == "Our Lady"


# ---- Separate verification and approval -------------------------------------------------------------------
def test_a_supplied_text_cannot_be_verified_until_its_source_and_rights_are_recorded(application, run, editor):
    run("--execute")
    detail = editor.get(f"{BASE}/{next(d for d in editor.get(BASE).json() if d['slug'] == 'our-father')['id']}").json()
    latin_text = next(t for t in detail["texts"] if t["language"] == "la")
    assert latin_text["has_body"] and latin_text["rights_cleared"] is False
    assert any("Record whether the wording is public domain" in problem for problem in latin_text["problems"])
    refused = editor.post(f"{BASE}/{detail['id']}/texts/{latin_text['id']}/transition", json={"to": "source_verified"})
    assert refused.status_code == 409


def test_english_and_latin_keep_separate_states_and_approving_one_never_touches_the_other(application, run, editor, approver, reader):
    run("--execute")
    brief = next(d for d in editor.get(BASE).json() if d["slug"] == "our-father")
    detail = editor.get(f"{BASE}/{brief['id']}").json()
    english = next(t for t in detail["texts"] if t["language"] == "en")
    approve_text(editor, approver, detail, english)
    after = {t["language"]: t["status"] for t in editor.get(f"{BASE}/{brief['id']}").json()["texts"]}
    assert after == {"en": "approved", "la": "proposed"}
    dev = f"{BASE}/{brief['id']}/transition"
    for step, who in (("source_verified", editor), ("pending_approval", editor), ("approved", approver), ("published", approver)):
        move(who, dev, step)
    page = reader.get("/api/devotions/our-father")
    assert [t["language"] for t in page.json()["texts"]] == ["en"]
    assert "Pater noster" not in page.text and "qui es in caelis" not in page.text      # the unapproved Latin is not public


def test_changing_a_supplied_text_invalidates_nothing_that_was_never_approved_but_changing_an_approved_one_does(application, run, editor, approver):
    devotion = make_devotion(editor, "filler")
    text = make_text(editor, devotion, language="la", body="Latin filler", is_translation=False)
    approve_text(editor, approver, devotion, text)
    edited = editor.patch(f"{BASE}/{devotion['id']}/texts/{text['id']}", json={"body": "Latin filler changed"}).json()
    assert edited["status"] == "proposed" and edited["approval_current"] is False


# ---- Nothing unapproved is public; nothing approved is overwritten -------------------------------------
def test_no_supplied_text_is_reachable_by_an_ordinary_reader(application, run, reader):
    run("--execute")
    assert reader.get("/api/devotions").json() == []
    for item in DATA["texts"]:
        response = reader.get(f"/api/devotions/{item['devotion_slug']}")
        assert response.status_code == 404 and item["body"][:20] not in response.text
    assert reader.get("/api/editorial/devotions").status_code == 403                   # and the inventory is for editors only


def test_a_user_supplied_text_never_replaces_wording_that_is_already_held():
    held = [{"devotion_slug": "our-father", "slot": "main", "language": "la", "body": "Wording already held", "source_title": "x"}]
    with pytest.raises(seed.Refused):
        seed.merge_user_supplied(held)


def test_seeding_again_over_an_approved_latin_text_leaves_it_alone(application, run, editor):
    from datetime import UTC, datetime
    from uuid import UUID
    run("--execute")
    brief = next(d for d in editor.get(BASE).json() if d["slug"] == "our-father")
    latin_text = next(t for t in editor.get(f"{BASE}/{brief['id']}").json()["texts"] if t["language"] == "la")
    with application.state.session_factory.begin() as db:        # an earlier, approved decision on this text
        row = db.get(PrayerText, UUID(latin_text["id"]))
        row.body, row.license_status, row.source_url = "Approved Latin filler", "public_domain", "https://example.org/edition"
        row.status, row.approved_by, row.approved_at, row.approved_hash = "approved", "user_approver", datetime.now(UTC), "recorded-earlier"
        row.source_verified_by, row.source_verified_at = "user_editor", datetime.now(UTC)
    run("--execute", "--add-missing-texts")
    kept = latin(application)["our-father"]
    assert (kept.body, kept.status, kept.approved_by, kept.approved_hash) == ("Approved Latin filler", "approved", "user_approver", "recorded-earlier")
