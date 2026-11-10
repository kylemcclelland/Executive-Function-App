# ruff: noqa: E501, F811
"""The user-supplied Latin prayers: verbatim import, provenance, independence from English, and no public exposure."""

import hashlib
import json
import sys
from pathlib import Path

import pytest
from sqlalchemy import select
from test_devotions import reader  # noqa: F401

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


# ---- Separate verification and approval -------------------------------------------------------------------

# ---- Nothing unapproved is public; nothing approved is overwritten -------------------------------------

def test_a_user_supplied_text_never_replaces_wording_that_is_already_held():
    held = [{"devotion_slug": "our-father", "slot": "main", "language": "la", "body": "Wording already held", "source_title": "x"}]
    with pytest.raises(seed.Refused):
        seed.merge_user_supplied(held)


def test_regina_caeli_is_dev_007_under_our_lady_with_latin_only(application, run, reader):
    run("--execute")
    brief = next(d for d in reader.get("/api/devotions").json() if d["slug"] == "regina-caeli")
    assert brief["category"] == "Our Lady" and brief["has_text"] is True
    detail = reader.get("/api/devotions/regina-caeli").json()
    assert [(t["language"], t["has_wording"], t["source"]["license_status"]) for t in detail["texts"]] == [("la", True, "unverified")]   # English is unavailable, not generated
    seeded = next(d for d in seed.load_drafts() if d["slug"] == "regina-caeli")
    assert seeded["code"] == "DEV-007" and seeded["category"] == "Our Lady"


def test_the_supplied_latin_is_readable_in_the_library_beside_the_english_with_its_source(application, run, reader):
    run("--execute")
    import latin_normalization
    normalized = {slug: r["normalized"] for slug, r in latin_normalization.apply_all(DATA).items()}
    for item in DATA["texts"]:
        detail = reader.get(f"/api/devotions/{item['devotion_slug']}").json()
        by_language = {t["language"]: t for t in detail["texts"]}
        assert by_language["la"]["body"] == normalized[item["devotion_slug"]]                          # the normalized supplied wording, exactly
        assert by_language["la"]["source"]["title"] == "User-supplied Latin text" and by_language["la"]["source"]["license_status"] == "unverified"
        if item["devotion_slug"] != "regina-caeli":
            assert by_language["en"]["has_wording"] is True                                             # English and Latin are separate texts
