# ruff: noqa: E501, F811
"""The ten foundational devotions as unpublished drafts: idempotent, never overwriting, no invented wording."""

import hashlib
import re
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from test_devotions import reader  # noqa: F401

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "seed_data"))

import devotion_drafts  # noqa: E402
import seed_devotion_drafts as seed  # noqa: E402

from app.models import Devotion, DevotionEvent, PrayerText  # noqa: E402
from app.services.devotions import has_body  # noqa: E402

TEN = [
    ("DEV-001", "sign-of-the-cross", "Sign of the Cross", "Daily Prayer"),
    ("DEV-002", "our-father", "Our Father", "Our Lord"),
    ("DEV-003", "hail-mary", "Hail Mary", "Our Lady"),
    ("DEV-004", "glory-be", "Glory Be", "Daily Prayer"),
    ("DEV-005", "apostles-creed", "Apostles’ Creed", "Daily Prayer"),
    ("DEV-006", "the-angelus", "The Angelus", "Our Lady"),
    ("DEV-007", "regina-caeli", "Regina Caeli", "Our Lady"),
    ("DEV-008", "the-holy-rosary", "The Holy Rosary", "Our Lady"),
    ("DEV-009", "examination-of-conscience", "Examination of Conscience", "Daily Prayer"),
    ("DEV-010", "act-of-contrition", "Act of Contrition", "Daily Prayer"),
    ("DEV-011", "prayer-to-st-michael", "Prayer to St. Michael", "Saints"),
]


@pytest.fixture
def run(application, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", application.state.settings.database_url)

    def go(*flags):
        code = seed.main(list(flags))
        return code, capsys.readouterr().out
    return go


def rows(application, model):
    with application.state.session_factory() as db:
        return db.scalars(select(model)).all()


def counts(application):
    with application.state.session_factory() as db:
        return [db.scalar(select(func.count()).select_from(model)) for model in (Devotion, PrayerText, DevotionEvent)]


# ---- The ten drafts --------------------------------------------------------------------------------------

def test_the_ten_devotions_and_their_categories_are_exactly_as_specified():
    assert [(d["code"], d["slug"], d["title"], d["category"]) for d in seed.load_drafts()] == TEN


def test_every_category_is_one_of_the_library_categories():
    allowed = {"Daily Prayer", "Our Lord", "Our Lady", "Saints", "Liturgical Seasons"}
    assert {d["category"] for d in seed.load_drafts()} <= allowed


def test_a_dry_run_changes_nothing_but_reports_what_would_happen(application, run):
    before = counts(application)
    code, output = run()
    assert code == 0 and "Would create 11 unpublished draft devotion(s)" in output and "Dry run only" in output
    assert counts(application) == before == [0, 0, 0]


def test_seeding_creates_the_devotions_and_approves_nothing_yet_all_are_readable(application, run, reader):
    code, output = run("--execute")
    assert code == 0 and "Nothing was verified, approved or published" in output
    devotions = rows(application, Devotion)
    assert sorted(d.slug for d in devotions) == sorted(slug for _, slug, _, _ in TEN)
    for d in devotions:
        assert (d.status, d.prose_origin, d.created_by) == ("proposed", "ai_draft", "seed:devotion-drafts-v1")
        assert d.approved_by is None and d.approved_hash is None and d.published_at is None and d.source_verified_by is None
    assert all(t.status == "proposed" and t.approved_by is None and t.source_verified_by is None for t in rows(application, PrayerText))
    assert sorted(d["slug"] for d in reader.get("/api/devotions").json()) == sorted(slug for _, slug, _, _ in TEN)    # no approval is needed to read them
    for _, slug, _, _ in TEN:
        assert reader.get(f"/api/devotions/{slug}").status_code == 200


def test_each_record_remembers_which_draft_it_was(application, run):
    run("--execute")
    with application.state.session_factory() as db:
        seeded = {e.note for e in db.scalars(select(DevotionEvent).where(DevotionEvent.action == "seeded"))}
    assert seeded == {code for code, *_ in TEN}


# ---- Idempotent, and it never overwrites -------------------------------------------------------------------

def test_running_it_again_duplicates_nothing(application, run):
    run("--execute")
    after_first = counts(application)
    code, output = run("--execute")
    assert code == 0 and "Created 0 unpublished draft devotion(s)" in output and "Created 0 proposed text record(s)" in output
    assert counts(application) == after_first


def test_a_devotion_that_exists_is_left_completely_untouched(application, run):
    run("--execute")
    with application.state.session_factory.begin() as db:
        devotion = db.scalar(select(Devotion).where(Devotion.slug == "our-father"))
        devotion.title = "Our Father (edited by an editor)"
        devotion.overview = "A reviewer's own words."
        devotion_id = devotion.id
    run("--execute")
    with application.state.session_factory() as db:
        devotion = db.get(Devotion, devotion_id)
        assert (devotion.title, devotion.overview) == ("Our Father (edited by an editor)", "A reviewer's own words.")


def test_a_removed_text_is_not_quietly_put_back_unless_asked(application, run):
    run("--execute")
    with application.state.session_factory.begin() as db:
        row = db.scalar(select(PrayerText).join(Devotion).where(Devotion.slug == "hail-mary", PrayerText.language == "en"))
        db.delete(row)
    run("--execute")
    hail_mary = next(d.id for d in rows(application, Devotion) if d.slug == "hail-mary")
    assert not [t for t in rows(application, PrayerText) if t.devotion_id == hail_mary and t.language == "en"]
    code, output = run("--execute", "--add-missing-texts")
    assert code == 0 and "Created 0 unpublished draft devotion(s)" in output and "Created 1 proposed text record(s)" in output


# ---- No wording is invented -----------------------------------------------------------------------------

def test_the_draft_module_contains_no_prayer_wording():
    drafted = " ".join(
        [d["overview"] or "" for d in seed.load_drafts()] + [i for d in seed.load_drafts() for i in d["instructions"]]
        + [str(s) for d in seed.load_drafts() for s in d["steps"]]
    )
    for entry in seed.load_texts(seed.load_drafts()):
        for sentence in re.split(r"(?<=[.!?:;])\s+", entry["body"]):
            if len(sentence) > 30:
                assert sentence not in drafted, f"prayer wording found in the draft prose: {sentence[:40]}"


def test_every_text_with_wording_names_its_source_and_has_cleared_rights(application, run):
    run("--execute")
    for row in rows(application, PrayerText):
        assert row.source_title and row.attribution and row.source_authority, (row.slot, row.language)
        if row.source_title == "User-supplied Latin text":
            # supplied in a file that names no source and no rights: recorded as exactly that, never as cleared
            assert has_body(row) and row.language == "la" and row.license_status == "unverified" and row.source_url is None and row.source_date is None
            assert "latin_prayers_file.txt" in row.license_notes and "SHA-256" in row.license_notes
            continue
        if row.source_title == "User-supplied text":
            # typed by the owner in a message that names no source and no rights: recorded as exactly that, never as cleared
            assert has_body(row) and row.license_status == "unverified" and row.source_url is None and row.source_date is None
            assert "message names no author" in row.license_notes and "SHA-256" in row.license_notes
            continue
        if row.source_title.startswith("User-supplied document: The Prayers of the Rosary"):
            # supplied in a document that names no author, edition or rights: recorded as exactly that, never as cleared
            assert has_body(row) and row.slot.startswith("collection-") and row.license_status == "unverified" and row.source_url is None and row.source_date is None
            assert "The Prayers of the Rosary.txt" in row.license_notes and "SHA-256" in row.license_notes
            continue
        assert row.source_url and row.source_date, (row.slot, row.language)
        if has_body(row):
            assert row.license_status == "public_domain" and row.source_retrieved_at is not None
        else:
            assert row.license_status in {"restricted", "unverified"}


def test_withheld_wording_is_really_empty_and_says_why(application, run):
    run("--execute")
    withheld = [t for t in rows(application, PrayerText) if not has_body(t)]
    assert len(withheld) == 3                                    # the five supplied Latin texts replaced five citations
    for row in withheld:
        assert row.body == "" and row.license_status == "restricted" and "withheld" in row.license_notes.lower()


def test_stored_wording_still_matches_the_hash_recorded_when_it_was_copied(application, run):
    run("--execute")
    checked = 0
    for row in rows(application, PrayerText):
        if has_body(row):
            recorded = re.search(r"wording SHA-256 ([0-9a-f]{64})", row.license_notes)
            assert recorded, (row.slot, row.language)
            assert hashlib.sha256(row.body.encode("utf-8")).hexdigest() == recorded.group(1)
            checked += 1
    assert checked == 38                           # 18 earlier texts and the 20 of the Rosary document


def test_english_and_latin_are_separate_independently_sourced_records(application, run):
    run("--execute")
    with application.state.session_factory() as db:
        for slug in ("our-father", "hail-mary", "glory-be", "apostles-creed", "act-of-contrition"):
            texts = {t.language: t for t in db.scalar(select(Devotion).where(Devotion.slug == slug)).texts}
            assert set(texts) == {"en", "la"}
            assert texts["en"].source_url != texts["la"].source_url           # never one derived from the other
            assert texts["en"].source_title != texts["la"].source_title
            assert has_body(texts["en"]) and has_body(texts["la"]) == (slug != "act-of-contrition")   # no Latin was supplied for the Act of Contrition
        salve = {t.language: t for t in db.scalar(select(Devotion).where(Devotion.slug == "the-holy-rosary")).texts if t.slot == "hail-holy-queen"}
        assert has_body(salve["en"]) and has_body(salve["la"]) and salve["en"].source_title != salve["la"].source_title


def test_sources_with_no_real_source_get_no_record(application, run):
    run("--execute")
    slugs = {d.id: d.slug for d in rows(application, Devotion)}
    slots = {(slugs[t.devotion_id], t.slot, t.language) for t in rows(application, PrayerText)}
    assert ("the-holy-rosary", "fatima-prayer", "en") not in slots and ("prayer-to-st-michael", "main", "la") not in slots


def test_no_wording_appears_in_the_editorial_log(application, run):
    run("--execute")
    log = " ".join(e.note or "" for e in rows(application, DevotionEvent))
    for row in rows(application, PrayerText):
        if has_body(row):
            assert row.body[:40] not in log


# ---- The Holy Rosary ------------------------------------------------------------------------------------

def test_the_rosary_reuses_the_other_devotions_prayers_and_marks_its_optional_customs(application, run):
    run("--execute")
    with application.state.session_factory() as db:
        rosary = db.scalar(select(Devotion).where(Devotion.slug == "the-holy-rosary"))
        steps = rosary.steps
        assert len(steps) == 5 + 4 * 5 * 5 + 3 and rosary.choice_label == "Mysteries"
        groups = [s["group"] for s in steps if s["group"]]
        assert sorted(set(groups)) == ["Glorious Mysteries", "Joyful Mysteries", "Luminous Mysteries", "Sorrowful Mysteries"]
        assert all(groups.count(name) == 25 for name in set(groups))                       # five decades of five steps each
        slugs = {s["devotion_slug"] for s in steps if s["devotion_slug"]}
        assert slugs == {"sign-of-the-cross", "apostles-creed", "our-father", "hail-mary", "glory-be"}
        assert {s["text_slot"] for s in steps if s["text_slot"] and not s["devotion_slug"]} == {"hail-holy-queen", "rosary-concluding-prayer", "fatima-prayer"}
        assert {s["title"] for s in steps if s["optional"]} == {"Three Hail Marys", "Fátima prayer", "Sign of the Cross"}
        assert all(s["repeat"] == 10 for s in steps if s["title"] == "Hail Mary")
        own = {t.slot for t in rosary.texts}
        assert {"hail-holy-queen", "rosary-concluding-prayer"} <= own and "fatima-prayer" not in own
        mysteries = [s["title"] for s in steps if s["kind"] == "instruction" and s["group"] == "Joyful Mysteries"]
        assert mysteries == ["1. The Annunciation", "2. The Visitation", "3. The Nativity", "4. The Presentation", "5. The Finding in the Temple"]


# ---- Refusals ------------------------------------------------------------------------------------------

def test_it_refuses_a_database_that_is_not_migrated_far_enough(application, run):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with application.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0010")
    code, output = run("--execute")
    assert code == 1 and "STOP" in output and "run the migrations first" in output


def test_it_refuses_a_sqlite_database_that_holds_user_data(application, run):
    if application.state.engine.dialect.name != "sqlite":
        pytest.skip("SQLite-only guard")
    with application.state.engine.begin() as connection:
        connection.execute(text("INSERT INTO users (id, timezone, created_at, updated_at) VALUES ('00000000000000000000000000000001', 'UTC', '2026-01-01', '2026-01-01')"))
    before = counts(application)
    code, output = run("--execute")
    assert code == 1 and "holds user data" in output and counts(application) == before


def test_a_local_sqlite_database_with_user_data_is_seeded_only_when_explicitly_allowed_and_the_user_data_is_untouched(application, run):
    if application.state.engine.dialect.name != "sqlite":
        pytest.skip("SQLite-only guard")
    with application.state.engine.begin() as connection:
        connection.execute(text("INSERT INTO users (id, timezone, created_at, updated_at) VALUES ('00000000000000000000000000000001', 'UTC', '2026-01-01', '2026-01-01')"))
    def users():
        with application.state.engine.connect() as connection:
            return sorted(map(tuple, connection.execute(text("SELECT * FROM users")).all()))
    before = users()
    code, output = run("--execute", "--allow-sqlite-with-user-data")
    assert code == 0 and "Created 11 unpublished draft devotion(s)" in output
    assert users() == before                                                         # the user's own rows are exactly as they were
    with application.state.session_factory() as db:
        assert {d.status for d in db.scalars(select(Devotion))} == {"proposed"}      # nothing approved or published
        assert all(t.approved_by is None and t.source_verified_by is None for t in db.scalars(select(PrayerText)))
    code, output = run("--execute", "--allow-sqlite-with-user-data")                 # idempotent
    assert code == 0 and "Created 0 unpublished draft devotion(s)" in output and "Created 0 proposed text record(s)" in output


def test_the_database_url_is_never_taken_from_the_command_line(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert seed.main([]) == 2
    assert "not accepted on the command line" in capsys.readouterr().out


def test_the_draft_data_is_validated_by_the_same_rules_as_the_editorial_api():
    from app.schemas import devotions as schemas
    for item in devotion_drafts.DRAFTS:
        schemas.DevotionCreate(**{k: v for k, v in item.items() if k != "code"})


# ---- The first six (DEV-001 to DEV-006) ---------------------------------------------------------------------
SIX = "DEV-001,DEV-002,DEV-003,DEV-004,DEV-005,DEV-006"


def test_the_codes_option_creates_only_the_six_and_never_the_rest(application, run):
    code, output = run("--execute", "--codes", SIX)
    assert code == 0 and "Created 6 unpublished draft devotion(s)" in output
    assert sorted(d.slug for d in rows(application, Devotion)) == sorted(["sign-of-the-cross", "our-father", "hail-mary", "glory-be", "apostles-creed", "the-angelus"])
    assert len(rows(application, PrayerText)) == 12                                  # English and Latin for each, nothing for the others
    again, output = run("--execute", "--codes", SIX)
    assert again == 0 and "Created 0 unpublished draft devotion(s)" in output       # idempotent
    full, output = run("--execute")                                                 # the rest can follow later, leaving the six untouched
    assert full == 0 and "Created 5 unpublished draft devotion(s)" in output


def test_an_unknown_code_is_refused(application, run):
    code, output = run("--execute", "--codes", "DEV-001,DEV-999")
    assert code == 1 and "Unknown draft code" in output and counts(application) == [0, 0, 0]


def test_the_six_carry_a_historical_introduction_a_purpose_occasions_and_citations():
    for item in seed.load_drafts({f"DEV-00{n}" for n in range(1, 7)}):
        assert item["background"] and item["significance"] and item["references"], item["slug"]
        assert any(line.startswith("Traditional occasions:") for line in item["instructions"]), item["slug"]


def test_the_dossier_document_matches_the_data_and_contains_no_wording():
    import build_dossiers
    doc = (Path(__file__).resolve().parents[2] / "docs" / "devotion-dossiers.md").read_text(encoding="utf-8")
    original = build_dossiers.OUT
    try:
        import tempfile
        build_dossiers.OUT = Path(tempfile.mkdtemp()) / "dossiers.md"
        build_dossiers.main()
        assert build_dossiers.OUT.read_text(encoding="utf-8") == doc, "docs/devotion-dossiers.md is out of date: run build_dossiers.py"
    finally:
        build_dossiers.OUT = original
    for entry in seed.load_texts(seed.load_drafts()):
        if entry["body"]:
            assert entry["body"][:30] not in doc
    for number in range(1, 7):
        assert f"DEV-00{number}" in doc
    assert doc.count("Not approved") >= 12 and "unapproved editorial prose" in doc.lower()
