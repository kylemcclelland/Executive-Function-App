# ruff: noqa: E501
"""The Devotion Library importer: package parsing, UTF-8/Greek preservation, duplicate detection,
dry-run guarantees, idempotent writes and the editorial hold on review-only entries."""

import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import import_devotion_library as importer  # noqa: E402

from app.models import Devotion, DevotionEvent, PrayerText  # noqa: E402

GREEK = "Ἅγιος ὁ Θεός, Ἅγιος Ἰσχυρός,\nἍγιος Ἀθάνατος, ἐλέησον ἡμᾶς."


def entry(slug, title, *, ready="true", languages=("el", "en"), english="Holy God, Holy Mighty,\nHoly Immortal, have mercy on us.", original=GREEK, themes=("Trinity",)):
    lang_lines = "\n".join(f'  - "{code}"' for code in languages)
    theme_lines = "\n".join(f'  - "{t}"' for t in themes)
    front = f'''---
id: {slug}
title: "{title}"
alternate_titles: []
attribution: "Traditional"
attribution_confidence: "low"
original_language: "Greek"
included_languages:
{lang_lines}
translation_author: "Test translator"
translation_type: traditional
tradition: "Byzantine"
associated_churches: []
regional_associations: []
theological_themes:
{theme_lines}
devotional_focus: []
spiritual_purpose: []
prayer_form: "Short Prayer"
occasions: []
liturgical_season: "Any"
suggested_context: "Private prayer"
duration_min_minutes: 0.3
duration_max_minutes: 0.8
duration_basis: "test"
research_status: ready_with_qualifications
reuse_status: historical_public_domain
ready_for_import: {ready}
---

HISTORICAL INTRODUCTION:

A short history.

ORIGINAL-LANGUAGE TEXT:

{original if "el" in languages else "English-only historical text; no original-language text is included."}

ENGLISH TEXT:

{english}

TEXTUAL NOTES:

None.

SOURCES:

1. Test source book (1910), https://example.org/source

COPYRIGHT AND REUSE:

Public domain.

REMAINING UNCERTAINTIES:

None.
'''
    return front


def build_package(tmp_path, entries):
    (tmp_path / "byzantine").mkdir(exist_ok=True)
    rows = ['"id","title","filepath","tradition","included_languages","theological_themes","devotional_focus","duration_min_minutes","duration_max_minutes","research_status","reuse_status","original_text_source","translation_source","ready_for_import"']
    for slug, title, kwargs in entries:
        path = tmp_path / "byzantine" / f"{slug}.txt"
        path.write_text(entry(slug, title, **kwargs), encoding="utf-8")
        ready = kwargs.get("ready", "true")
        rows.append(f'"{slug}","{title}","byzantine/{slug}.txt","Byzantine","el;en","Trinity","Focus","0.3","0.8","ready_with_qualifications","historical_public_domain","Test","Test","{ready}"')
    (tmp_path / "manifest.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return tmp_path


def relaxed_counts(monkeypatch, total, ready):
    monkeypatch.setattr(importer, "EXPECTED_TOTAL", total)
    monkeypatch.setattr(importer, "EXPECTED_READY", ready)


def db_state(application):
    with application.state.session_factory() as db:
        return (db.scalar(select(func.count()).select_from(Devotion)), db.scalar(select(func.count()).select_from(PrayerText)),
                db.scalar(select(func.count()).select_from(DevotionEvent)))


def test_parsing_preserves_greek_and_line_breaks(tmp_path):
    build_package(tmp_path, [("trisagion", "Trisagion", {})])
    front, sections = importer.parse_file(tmp_path / "byzantine" / "trisagion.txt")
    assert front["title"] == "Trisagion" and front["ready_for_import"] is True
    assert front["included_languages"] == ["el", "en"] and front["duration_max_minutes"] == 0.8
    assert sections["ORIGINAL-LANGUAGE TEXT"] == GREEK                     # Greek and its line break survive exactly
    assert "\n" in sections["ENGLISH TEXT"]


def test_dry_run_default_leaves_the_database_unchanged(application, tmp_path, monkeypatch):
    relaxed_counts(monkeypatch, 1, 1)
    build_package(tmp_path, [("trisagion", "Trisagion", {})])
    before = db_state(application)
    counts = importer.run(tmp_path, application.state.session_factory, execute=False)
    assert counts["NEW"] == 1 and counts["written"] == 0
    assert db_state(application) == before


def test_execute_imports_drafts_idempotently_and_holds_review_entries(application, tmp_path, monkeypatch):
    relaxed_counts(monkeypatch, 2, 1)
    build_package(tmp_path, [("trisagion", "Trisagion", {}), ("held-prayer", "Held Prayer", {"ready": "false"})])
    counts = importer.run(tmp_path, application.state.session_factory, execute=True)
    assert counts["written"] == 1 and counts["REVIEW_ONLY"] == 1
    with application.state.session_factory() as db:
        devotion = db.scalar(select(Devotion).where(Devotion.slug == "trisagion"))
        assert devotion.status == "proposed" and devotion.discovery["tradition"] == "Byzantine"
        assert devotion.discovery["theological_themes"] == ["Trinity"] and devotion.discovery["duration_max_minutes"] == 0.8
        texts = {t.language: t for t in db.scalars(select(PrayerText).where(PrayerText.devotion_id == devotion.id))}
        assert texts["el"].body == GREEK and texts["en"].is_translation is True
        assert all(t.status == "proposed" for t in texts.values())
        assert db.scalar(select(Devotion.id).where(Devotion.slug == "held-prayer")) is None
    # Running again changes nothing: the existing draft is detected and skipped.
    after_first = db_state(application)
    again = importer.run(tmp_path, application.state.session_factory, execute=True)
    assert again["written"] == 0 and again["EXISTING_IDENTICAL"] == 1
    assert db_state(application) == after_first


def test_duplicates_by_title_and_different_text_are_never_overwritten(application, tmp_path, monkeypatch):
    relaxed_counts(monkeypatch, 2, 2)
    with application.state.session_factory.begin() as db:
        existing = Devotion(id=uuid4(), slug="the-trisagion", title="The  TRISAGION", overview="x", status="proposed", created_by="test")
        db.add(existing)
        db.flush()
        db.add(PrayerText(devotion_id=existing.id, slot="main", language="en", body="A different wording entirely.", status="proposed", entered_by="test"))
    build_package(tmp_path, [("trisagion", "The Trisagion", {}), ("brand-new", "Brand New Prayer", {})])
    counts = importer.run(tmp_path, application.state.session_factory, execute=True)
    assert counts["EXISTING_DIFFERENT"] == 1 and counts["NEW"] == 1 and counts["written"] == 1
    with application.state.session_factory() as db:
        assert db.scalar(select(PrayerText.body).join(Devotion, Devotion.id == PrayerText.devotion_id).where(Devotion.slug == "the-trisagion")) == "A different wording entirely."
        assert db.scalar(select(Devotion.id).where(Devotion.slug == "brand-new")) is not None


def test_invalid_entries_and_count_mismatch_block_writes(application, tmp_path, monkeypatch):
    relaxed_counts(monkeypatch, 2, 2)                                      # the package will disagree
    build_package(tmp_path, [("bad-themes", "Bad Themes", {"themes": ("NotATheme",)})])
    before = db_state(application)
    counts = importer.run(tmp_path, application.state.session_factory, execute=True)
    assert counts["INVALID"] == 1 and "warning" in counts and counts["written"] == 0
    assert db_state(application) == before


def test_the_real_package_validates_as_19_ready_and_3_held():
    package = Path("C:/Users/uvaga/Downloads/optima-pars-devotions")
    if not package.is_dir():
        import pytest
        pytest.skip("research package not present on this machine")
    candidates = importer.load_package(package)
    assert len(candidates) == 22
    assert sum(c.ready for c in candidates) == 19
    assert {c.slug for c in candidates if not c.ready} == importer.NEVER_IMPORT
    assert all(not c.problems for c in candidates if c.ready)              # zero validation errors among the eligible
