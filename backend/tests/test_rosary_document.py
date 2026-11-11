# ruff: noqa: E501, F811
"""The Prayers of the Rosary document: exact import, provenance, no overwriting, and nothing unreviewed is public."""

import hashlib
import json
import re
import sys
from pathlib import Path

import pytest
from sqlalchemy import select
from test_devotions import reader  # noqa: F401

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "seed_data"))

import import_rosary_prayers as importer  # noqa: E402
import seed_devotion_drafts as seed  # noqa: E402

from app.models import Devotion, PrayerText  # noqa: E402

DATA = json.loads((SCRIPTS / "seed_data" / "rosary_document.json").read_text(encoding="utf-8"))
SOURCE_FILE = Path("C:/Users/uvaga/Downloads/The Prayers of the Rosary.txt")
FILE_SHA = "9bf41f324427ee093dd15bec91f948678b46a378d26f16522255b15354db7c74"
KEYS = ["sign-of-the-cross", "apostles-creed", "our-father", "hail-mary", "glory-be", "fatima-prayer", "hail-holy-queen", "closing-prayer", "st-michael-prayer", "st-joseph-prayer"]
by_key = {p["key"]: p for p in DATA["prayers"]}


@pytest.fixture
def run(application, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", application.state.settings.database_url)

    def go(*flags):
        code = seed.main(list(flags))
        return code, capsys.readouterr().out
    return go


def collection_rows(application):
    with application.state.session_factory() as db:
        rosary = db.scalar(select(Devotion).where(Devotion.slug == "the-holy-rosary"))
        return {(t.slot, t.language): t for t in rosary.texts if t.slot.startswith(seed.COLLECTION_PREFIX)}


def words(value):
    return re.findall(r"\S+", value)


# ---- 1. Import accuracy, checked independently of the importer ---------------------------------------------------

def test_all_ten_prayers_were_found_in_the_documents_order():
    assert [p["key"] for p in DATA["prayers"]] == KEYS
    assert [p["heading_in_file"] for p in DATA["prayers"]] == ["The Sign of the Cross", "The Apostles' Creed", "The Our Father", "The Hail Mary", "The Glory Be", "The Fatima Prayer", "The Hail Holy Queen", "The Closing Prayer", "St. Michael the Archangel Prayer", "Prayer to St. Joseph"]
    assert DATA["file_sha256"] == FILE_SHA and DATA["filename"] == "The Prayers of the Rosary.txt"
    assert "Pronouncing the Rosary in Latin" in DATA["not_imported"]          # advice, not a prayer: named, not imported


@pytest.mark.skipif(not SOURCE_FILE.exists(), reason="the original document is not on this machine")
def test_every_imported_wording_matches_the_document_word_for_word_and_nothing_else_was_taken():
    raw = SOURCE_FILE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FILE_SHA
    reparsed = importer.parse(raw)
    reparsed["filename"] = SOURCE_FILE.name
    assert reparsed == DATA                                                      # the stored data is exactly what the document yields
    # Independently: drop only the standalone page numbers, then every body's words must be one unbroken run of the document's words.
    lines = [line for line in raw.decode("utf-8").splitlines() if not re.fullmatch(r"\s*\d{1,2}\s*", line)]
    document = words("\n".join(lines))
    for prayer in DATA["prayers"]:
        for field in ("english", "latin"):
            run_of_words = words(prayer[field])
            hits = [i for i in range(len(document) - len(run_of_words) + 1) if document[i:i + len(run_of_words)] == run_of_words]
            assert len(hits) == 1, (prayer["key"], field)
    # Nothing but structure is left once every body, introduction and note is removed from the document.
    left = " ".join(document)
    for prayer in DATA["prayers"]:
        for piece in (prayer["english"], prayer["latin"], prayer["introduction"], *prayer["commentary_lines"]):
            left = left.replace(" ".join(words(piece)), "", 1)
    left = left.replace(" ".join(words(DATA["document_introduction"])), "", 1)
    remaining = {w for w in words(left)}
    assert remaining <= set(words(" ".join([p["heading_in_file"] + " " + p["latin_title"] for p in DATA["prayers"]] + ["EN · LA English Latina Pronouncing the Rosary in Latin The Prayers of the Rosary Full page:"]))) | set(words(
        "Ecclesiastical Latin, the Latin of the Church's prayer, is pronounced consistently, much as Italian is, with no silent letters, which makes it easier to learn than Classical Latin. The complete guide, with the sound of every letter and the key prayers spelled out phonetically, is on the Latin Rosary page, which also reads each prayer aloud in Latin so you can learn it by ear. St. Michael Prayer Prayer to St. Joseph "
        "The Apostles’ Creed, Symbolum Apostolorum Hail Mary Prayer, Ave Maria (with word-by-word translation) Hail Holy Queen, Salve Regina St. Michael the Archangel Prayer (history, theology, Latin pronunciation)"))


def test_the_wording_keeps_what_the_document_has():
    assert by_key["hail-holy-queen"]["english"].endswith("\nV. Pray for us, O holy Mother of God.\nR. That we may be made worthy of the promises of Christ.")
    assert by_key["hail-holy-queen"]["latin"].endswith("\nV. Ora pro nobis, sancta Dei Genitrix.\nR. Ut digni efficiamur promissionibus Christi.")
    assert "Iesum Christum" in by_key["apostles-creed"]["latin"] and "Iesus." in by_key["hail-mary"]["latin"]                  # spelling is the document's, not harmonised
    assert "ab igne inferni" in by_key["fatima-prayer"]["latin"] and "inferiori" not in by_key["fatima-prayer"]["latin"]      # the note's other variant is not blended in
    assert by_key["fatima-prayer"]["commentary_lines"][0].startswith("Note: A second widely-used variant")                # kept as commentary, apart from the wording
    assert by_key["sign-of-the-cross"] == {**by_key["sign-of-the-cross"], "english": "In the name of the Father, and of the Son, and of the Holy Spirit. Amen.", "latin": "In nomine Patris, et Filii, et Spiritus Sancti. Amen."}
    assert all("\r" not in p[f] and not re.search(r"(?m)^\d{1,2}$", p[f]) for p in DATA["prayers"] for f in ("english", "latin"))   # no stray page numbers or carriage returns


def test_the_importer_refuses_a_document_it_cannot_slice_safely():
    with pytest.raises(SystemExit):
        importer.parse(b"The Prayers of the Rosary\nThe Sign of the Cross\nSignum Crucis\n")
    raw = SOURCE_FILE.read_bytes() if SOURCE_FILE.exists() else None
    if raw is not None:
        with pytest.raises(SystemExit):
            importer.parse(raw.replace(b"Latina", b"Latin", 1))                  # a missing language marker
        with pytest.raises(SystemExit):
            importer.parse(raw.replace(b"The Glory Be\r\n", b"", 1))             # a missing prayer


# ---- 2. What seeding records ---------------------------------------------------------------------------------------

def test_each_prayer_is_recorded_on_the_holy_rosary_with_its_provenance_unverified_and_unapproved(application, run):
    assert run("--execute")[0] == 0
    rows = collection_rows(application)
    assert len(rows) == 20 and {slot for slot, _ in rows} == {seed.COLLECTION_PREFIX + key for key in KEYS}
    for position, key in enumerate(KEYS):
        for language, field in (("en", "english"), ("la", "latin")):
            row = rows[(seed.COLLECTION_PREFIX + key, language)]
            assert row.body == by_key[key][field] and row.position == position                       # exact wording, in the document's order
            assert (row.status, row.license_status, row.source_title) == ("proposed", "unverified", DATA["provenance"])
            assert row.source_verified_by is None and row.approved_by is None and row.approved_hash is None
            assert FILE_SHA in row.license_notes and DATA["filename"] in row.source_edition + row.attribution + row.license_notes
            assert f"Stored wording SHA-256 {hashlib.sha256(row.body.encode()).hexdigest()}" in row.license_notes
            assert "source commentary, not prayer text" in row.license_notes and by_key[key]["introduction"] in row.license_notes
            assert "names no author" in row.attribution


def test_existing_records_are_reused_not_duplicated_and_no_earlier_wording_is_touched(application, run):
    with application.state.session_factory() as db:
        assert db.scalar(select(Devotion).where(Devotion.slug == "the-holy-rosary")) is None
    run("--execute")
    before_devotions = None
    with application.state.session_factory() as db:
        slugs = sorted(d.slug for d in db.scalars(select(Devotion)))
        assert slugs == sorted(d["slug"] for d in seed.devotion_drafts.DRAFTS)           # no devotion was added for any of the ten prayers
        assert "prayer-to-st-joseph" not in slugs
        rosary = db.scalar(select(Devotion).where(Devotion.slug == "the-holy-rosary"))
        own = {(t.slot, t.language): t.body for t in rosary.texts if not t.slot.startswith(seed.COLLECTION_PREFIX)}
        sources = {(t["slot"], t["language"]): t["body"] for t in json.loads((SCRIPTS / "seed_data" / "prayer_sources.json").read_text(encoding="utf-8"))["texts"] if t["devotion_slug"] == "the-holy-rosary"}
        assert own == sources                                                              # the Rosary's earlier prayer texts are exactly as they were
        before_devotions = len(slugs)
        hail_mary = db.scalar(select(Devotion).where(Devotion.slug == "hail-mary"))
        assert {t.slot for t in hail_mary.texts} == {"main"}                                 # the Hail Mary devotion gained nothing
    run("--execute", "--add-missing-texts")
    with application.state.session_factory() as db:
        assert db.scalar(select(Devotion).where(Devotion.slug == "the-holy-rosary")) is not None
        assert db.query(Devotion).count() == before_devotions
        assert db.query(PrayerText).filter(PrayerText.slot.like(seed.COLLECTION_PREFIX + "%")).count() == 20     # seeding again duplicates nothing


def test_a_different_edition_already_held_is_noted_for_the_reviewer_and_never_replaced(application, run):
    run("--execute")
    with application.state.session_factory() as db:
        hail_mary_en = db.scalar(select(PrayerText).join(Devotion).where(Devotion.slug == "hail-mary", PrayerText.language == "en"))
        assert hail_mary_en.body != by_key["hail-mary"]["english"]                          # the editions really do differ
    note = collection_rows(application)[("collection-hail-mary", "en")].license_notes
    assert "Another edition of this prayer is held on the hail-mary devotion" in note and "Neither was changed" in note
    assert "Another edition" not in collection_rows(application)[("collection-sign-of-the-cross", "la")].license_notes    # identical wording: nothing to flag


# ---- 3. Review workflow and no public exposure -----------------------------------------------------------------------


def test_seeding_again_never_overwrites_a_collection_text_that_was_edited(application, run):
    run("--execute")
    with application.state.session_factory.begin() as db:
        row = db.scalar(select(PrayerText).where(PrayerText.slot == "collection-our-father", PrayerText.language == "en"))
        row.body = "A reviewer's own correction"
    run("--execute", "--add-missing-texts")
    assert collection_rows(application)[("collection-our-father", "en")].body == "A reviewer's own correction"


def test_the_prayers_are_in_the_library_in_the_documents_order_with_their_source_and_no_approval_needed(application, run, reader):
    run("--execute")
    detail = reader.get("/api/devotions/the-holy-rosary").json()
    collection = [t for t in detail["texts"] if t["slot"].startswith(seed.COLLECTION_PREFIX)]
    assert len(collection) == 20
    assert [(t["slot"].removeprefix(seed.COLLECTION_PREFIX), t["language"]) for t in collection] == [(k, language) for k in KEYS for language in ("en", "la")] or         sorted((t["slot"], t["language"]) for t in collection) == sorted((seed.COLLECTION_PREFIX + k, language) for k in KEYS for language in ("en", "la"))
    for t in collection:
        prayer = by_key[t["slot"].removeprefix(seed.COLLECTION_PREFIX)]
        assert t["body"] == prayer["english" if t["language"] == "en" else "latin"] and t["has_wording"] is True      # exact wording
        assert t["source"]["title"] == DATA["provenance"] and t["source"]["license_status"] == "unverified"             # provenance kept, rights not claimed
    assert "license_notes" not in collection[0]
    with application.state.session_factory() as db:
        assert all(t.approved_by is None and t.source_verified_by is None for t in db.scalars(select(PrayerText)))      # nothing was approved to make this visible
