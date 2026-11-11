# ruff: noqa: E501, F811
"""The authorized normalization of the user-supplied Latin: exactly what was authorized, nothing more, and unapproved."""

import difflib
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

import import_latin_prayers as importer  # noqa: E402
import latin_normalization as norm  # noqa: E402
import seed_devotion_drafts as seed  # noqa: E402

from app.models import Devotion, DevotionEvent, PrayerText  # noqa: E402
from app.services.devotions import text_fingerprint  # noqa: E402

DATA = json.loads((SCRIPTS / "seed_data" / "user_supplied_latin.json").read_text(encoding="utf-8"))
ORIGINAL_FILE = Path("C:/Users/uvaga/Downloads/latin_prayers_file.txt")
ORIGINAL = {t["devotion_slug"]: t["body"] for t in DATA["texts"]}
NORMALIZED = {slug: r["normalized"] for slug, r in norm.apply_all(DATA).items()}


@pytest.fixture
def run(application, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", application.state.settings.database_url)

    def go(*flags):
        return seed.main(list(flags)), capsys.readouterr().out
    return go


def latin_rows(application):
    with application.state.session_factory() as db:
        slugs = {d.id: d.slug for d in db.scalars(select(Devotion))}
        return {slugs[t.devotion_id]: t for t in db.scalars(select(PrayerText).where(PrayerText.language == "la", PrayerText.slot == "main"))}


def tokens(text):
    return re.split(r"\s+", text.replace("\r", "").strip())


# ---- 1. The holy name -------------------------------------------------------------------------------

def test_every_iesus_is_now_jesus_and_no_other_form_was_touched():
    for slug, original in ORIGINAL.items():
        normalized = NORMALIZED[slug]
        assert not re.search(r"\bIesus\b", normalized)
        assert len(re.findall(r"\bJesus\b", normalized)) == len(re.findall(r"\bJesus\b", original)) + len(re.findall(r"\bIesus\b", original))
        assert len(re.findall(r"\bIesum\b", normalized)) == len(re.findall(r"\bIesum\b", original))     # a different form: untouched
        assert len(re.findall(r"\bIesu\b", normalized)) == len(re.findall(r"\bIesu\b", original))
    assert len(re.findall(r"\bIesus\b", ORIGINAL["the-angelus"])) == 3 and len(re.findall(r"\bJesus\b", NORMALIZED["the-angelus"])) == 3
    assert "Iesum" in NORMALIZED["apostles-creed"] and "Iesu " in NORMALIZED["regina-caeli"]


def test_the_rule_matches_whole_words_only():
    # the rule itself, applied directly: a substring or another form is never replaced
    assert re.sub(r"\bIesus\b", "Jesus", "Iesus Iesusque xIesus Iesu Iesum") == "Jesus Iesusque xIesus Iesu Iesum"


# ---- 2. The identified problems -----------------------------------------------------------------------

def test_the_identified_typographical_problems_are_corrected():
    assert "\u00ad" in ORIGINAL["hail-mary"] and "\u00ad" not in NORMALIZED["hail-mary"] and "mulieribus," in NORMALIZED["hail-mary"]
    assert "caelos, sedet" in NORMALIZED["apostles-creed"] and "communionem, remissionem" in NORMALIZED["apostles-creed"]
    assert "caelos,sedet" not in NORMALIZED["apostles-creed"] and "communionem,remissionem" not in NORMALIZED["apostles-creed"]
    assert NORMALIZED["hail-mary"].startswith("Ave Maria, gratia plena,\n\nDominus tecum")             # supported by the selected edition
    for body in NORMALIZED.values():
        assert "\r" not in body and not any(line != line.rstrip(" \t") for line in body.split("\n")) and not body.endswith((" ", "\n"))


def test_the_comma_after_gratia_plena_is_justified_by_a_named_edition_and_other_commas_are_only_proposed():
    assert "Compendium of the Catechism of the Catholic Church" in norm.EDITION and "Appendix A" in norm.EDITION
    proposals = {(p[0], p[1]) for p in norm.PROPOSALS}
    assert any(slug == "hail-mary" and "Sancta Maria mater Dei" in now for slug, now in proposals)    # not applied
    assert "Sancta Maria mater Dei," in NORMALIZED["hail-mary"] and "Ave Maria," in NORMALIZED["hail-mary"]


# ---- 3. Nothing else changed -----------------------------------------------------------------------------

def test_exactly_the_authorized_words_changed_and_no_other_wording():
    allowed = {
        ("Iesus.", "Jesus."): 3, ("mulieri\u00adbus,", "mulieribus,"): 1, ("plena", "plena,"): 1,
        ("caelos,sedet", "caelos, sedet"): 1, ("communionem,remissionem", "communionem, remissionem"): 1,
    }
    seen = {}
    for slug, original in ORIGINAL.items():
        a, b = tokens(original), tokens(NORMALIZED[slug])
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
            if tag == "equal":
                continue
            key = (" ".join(a[i1:i2]), " ".join(b[j1:j2]))
            seen[key] = seen.get(key, 0) + 1
    assert seen == allowed, f"unexpected wording changes: {set(seen) ^ set(allowed)}"


def test_the_authorized_rules_must_apply_exactly_the_expected_number_of_times():
    with pytest.raises(SystemExit):
        norm.normalize("the-angelus", ORIGINAL["the-angelus"].replace("Iesus.", "Iesus. Iesus.", 1))   # a fourth occurrence: stop
    with pytest.raises(SystemExit):
        norm.normalize("glory-be", ORIGINAL["glory-be"] + "\r\n  ")                                    # unexpected extra whitespace: stop


def test_the_original_verbatim_transcription_and_its_provenance_are_preserved():
    assert DATA["file_sha256"] == "0e9258a9fff356bef4ed34438c8716cad03ce1c5cc08cd54f0de6f82dd777a8c" and DATA["filename"] == "latin_prayers_file.txt"
    assert "\r\n" in ORIGINAL["our-father"] and "\u00ad" in ORIGINAL["hail-mary"] and "Iesus" in ORIGINAL["the-angelus"]
    for item in DATA["texts"]:
        assert hashlib.sha256(item["body"].encode("utf-8")).hexdigest() == item["body_sha256"]


# ---- 4-6. English, independence, and no public exposure ----------------------------------------------------

def test_english_texts_and_the_unsupplied_latin_are_unchanged_and_the_latin_is_recorded_as_a_normalization(application, run):
    assert run("--execute")[0] == 0
    sources = {(t["devotion_slug"], t["slot"], t["language"]): t["body"] for t in json.loads((SCRIPTS / "seed_data" / "prayer_sources.json").read_text(encoding="utf-8"))["texts"]}
    with application.state.session_factory() as db:
        slugs = {d.id: d.slug for d in db.scalars(select(Devotion))}
        for row in db.scalars(select(PrayerText)):
            key = (slugs[row.devotion_id], row.slot, row.language)
            if row.slot.startswith("collection-") or row.source_title == "User-supplied text":
                continue                                                                  # the Rosary document and the owner-typed text have their own tests
            if row.language == "en":
                assert row.body == sources[key], key                                      # English untouched
            elif key[0] == "sign-of-the-cross":
                assert row.body == sources[key]                                           # the Latin not in the file, untouched
    for slug, row in latin_rows(application).items():
        if slug in NORMALIZED:
            assert row.body == NORMALIZED[slug] and row.status == "proposed" and row.source_verified_by is None and row.approved_by is None
            assert "Editorial normalization (latin-normalization-v1)" in row.license_notes and "latin_prayers_file.txt" in row.license_notes
            assert f"Original verbatim transcription SHA-256 {hashlib.sha256(ORIGINAL[slug].encode()).hexdigest()}" in row.license_notes
            assert f"stored wording SHA-256 {hashlib.sha256(row.body.encode()).hexdigest()}" in row.license_notes
            assert row.license_status == "unverified"                                     # a corrected spelling is not a verification


# ---- 7. Applying it to a database, and reimporting -----------------------------------------------------------

def make_old(application, slug, *, approved=False):
    """Put a Latin text into the state an earlier (verbatim) import left it in, optionally approved."""
    with application.state.session_factory.begin() as db:
        row = db.scalar(select(PrayerText).join(Devotion).where(Devotion.slug == slug, PrayerText.language == "la", PrayerText.slot == "main"))
        row.body = ORIGINAL[slug]
        if approved:
            row.license_status, row.source_url = "public_domain", "https://example.org/edition"
            row.source_verified_by = row.source_verified_at = None
            row.source_verified_by, row.source_verified_at = "user_editor", datetime.now(UTC)
            row.status, row.approved_by, row.approved_at, row.approved_hash = "approved", "user_approver", datetime.now(UTC), text_fingerprint(row)
        return row.id


def test_normalizing_a_database_discards_earlier_approval_and_logs_only_field_names(application, run):
    run("--execute")
    text_id = make_old(application, "hail-mary", approved=True)
    with application.state.session_factory() as db:
        before = text_fingerprint(db.get(PrayerText, text_id))
    code, output = run("--execute", "--normalize-latin")
    assert code == 0 and "Latin normalization: 1 changed (returned to proposed)" in output
    with application.state.session_factory() as db:
        row = db.get(PrayerText, text_id)
        assert row.body == NORMALIZED["hail-mary"] and text_fingerprint(row) != before    # the fingerprint was recalculated
        assert (row.status, row.approved_by, row.approved_at, row.approved_hash, row.source_verified_by) == ("proposed", None, None, None, None)
        events = [e for e in db.scalars(select(DevotionEvent).where(DevotionEvent.text_id == text_id)) if e.actor == "seed:latin-normalization-v1"]
        assert len(events) == 1 and events[0].from_status == "approved" and events[0].to_status == "proposed" and events[0].note == "latin-normalization-v1: body, license_notes"
        assert "Jesus" not in (events[0].note or "") and NORMALIZED["hail-mary"][:20] not in (events[0].note or "")


def test_a_dry_run_changes_nothing(application, run):
    run("--execute")
    text_id = make_old(application, "the-angelus", approved=True)
    code, output = run("--normalize-latin")
    assert code == 0 and "Dry run only" in output
    with application.state.session_factory() as db:
        row = db.get(PrayerText, text_id)
        assert row.body == ORIGINAL["the-angelus"] and row.status == "approved"


def test_a_text_edited_since_the_import_is_never_touched(application, run):
    run("--execute")
    with application.state.session_factory.begin() as db:
        row = db.scalar(select(PrayerText).join(Devotion).where(Devotion.slug == "glory-be", PrayerText.language == "la"))
        row.body = "A reviewer's own correction"
        text_id = row.id
    code, output = run("--execute", "--normalize-latin")
    assert code == 0 and "skipped glory-be: wording differs from the original import" in output
    with application.state.session_factory() as db:
        assert db.get(PrayerText, text_id).body == "A reviewer's own correction"


def test_normalizing_again_leaves_an_already_normalized_and_re_approved_text_alone(application, run):
    run("--execute")
    run("--execute", "--normalize-latin")                       # already normalized: nothing to do
    with application.state.session_factory.begin() as db:
        row = db.scalar(select(PrayerText).join(Devotion).where(Devotion.slug == "our-father", PrayerText.language == "la"))
        row.license_status, row.source_url = "public_domain", "https://example.org/edition"
        row.source_verified_by, row.source_verified_at = "user_editor", datetime.now(UTC)
        row.status, row.approved_by, row.approved_at, row.approved_hash = "approved", "user_approver", datetime.now(UTC), text_fingerprint(row)
        text_id = row.id
    code, output = run("--execute", "--normalize-latin")
    assert code == 0 and "0 changed" in output
    with application.state.session_factory() as db:
        row = db.get(PrayerText, text_id)
        assert row.status == "approved" and row.body == NORMALIZED["our-father"]


def test_reimporting_the_original_file_reproduces_the_original_and_cannot_undo_the_normalization(application, run, tmp_path, monkeypatch):
    assert "sqlalchemy" not in Path(importer.__file__).read_text(encoding="utf-8")                     # the importer never touches a database
    run("--execute")
    run("--execute", "--normalize-latin")
    if ORIGINAL_FILE.exists():
        monkeypatch.setattr(importer, "OUT", tmp_path / "again.json")
        assert importer.main([str(ORIGINAL_FILE)]) == 0
        again = json.loads((tmp_path / "again.json").read_text(encoding="utf-8"))
        assert again == DATA                                                                      # the same original, byte for byte
    # a database holding the normalized wording is unmoved by reimporting and re-seeding
    run("--execute", "--add-missing-texts")
    for slug, row in latin_rows(application).items():
        if slug in NORMALIZED:
            assert row.body == NORMALIZED[slug]


def test_a_changed_original_file_cannot_be_silently_normalized_as_if_it_were_the_same(tmp_path):
    forged = json.loads(json.dumps(DATA))
    forged["texts"][0]["body"] = forged["texts"][0]["body"] + " changed"
    with pytest.raises(SystemExit):
        norm.apply_all(forged)                                                                    # its hash no longer matches


def test_the_before_and_after_document_matches_the_data():
    doc = (Path(__file__).resolve().parents[2] / "docs" / "latin-normalization-diff.md").read_text(encoding="utf-8")
    assert doc == norm.render(DATA, norm.apply_all(DATA)), "docs/latin-normalization-diff.md is out of date: run latin_normalization.py"
    assert "Proposed, NOT applied" in doc and "Nothing was verified, approved or published" in doc


def test_corrected_latin_is_readable_beside_the_english_with_its_provenance(application, run, reader):
    run("--execute")
    detail = reader.get("/api/devotions/the-angelus").json()
    by_language = {t["language"]: t for t in detail["texts"]}
    assert by_language["la"]["body"] == NORMALIZED["the-angelus"] and "Iesus" not in by_language["la"]["body"]
    assert by_language["la"]["source"]["title"] == "User-supplied Latin text" and by_language["la"]["source"]["license_status"] == "unverified"
    assert by_language["en"]["has_wording"] is True and by_language["en"]["source"]["license_status"] == "public_domain"
