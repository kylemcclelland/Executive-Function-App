#!/usr/bin/env python
# ruff: noqa: E501
"""Import the Optima Pars Devotion Library research package into the Oratory as UNPUBLISHED drafts.

    python scripts/import_devotion_library.py "C:/Users/me/Downloads/optima-pars-devotions"            # dry run (default): validates, compares, prints the report, writes NOTHING
    python scripts/import_devotion_library.py <package_dir> --execute                                   # apply, only after the dry-run report was approved

Guarantees
  * Dry run by default; ``--execute`` is the only way anything is written, and then in one transaction.
  * Idempotent: a devotion that already exists (matched by slug, title or alternate title) is never
    touched — not its status, approvals, wording or metadata. Re-running creates no duplicates.
  * Only entries the manifest marks ``ready_for_import: true`` are ever importable; review-only
    entries are reported and refused even with ``--execute``.
  * Everything enters as ``proposed``: nothing is verified, approved or published here, because the
    editorial schema requires a named human for those steps. Discovery metadata (themes, tradition,
    durations, sources, rights) is preserved on the devotion's ``discovery`` JSON.
  * UTF-8 only; line breaks and non-Latin text are stored exactly as supplied.
  * It refuses a database that is not at the current migration head.
"""

import argparse
import csv
import math
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from sqlalchemy import select, text  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.db import make_engine, make_session_factory  # noqa: E402
from app.models import Devotion, PrayerText  # noqa: E402
from app.schemas import devotions as schemas  # noqa: E402
from app.services.devotions import record  # noqa: E402

HEAD_REVISION = "0016"
IMPORTED_BY = "import:devotion-library-batch-01"
EXPECTED_TOTAL, EXPECTED_READY = 22, 19
NEVER_IMPORT = {"prayer-of-st-ephrem", "gregory-of-narek-prayer-94-excerpt", "act-of-spiritual-communion"}
THEMES = {"Incarnation", "Trinity", "Christology", "Passion", "Resurrection", "Eucharist", "Holy Spirit", "Marian", "Divine Mercy", "Grace", "Faith", "Hope", "Charity",
          "Repentance", "Intercession", "Protection", "Sanctification", "Communion of Saints", "Eternal Life"}
SECTIONS = ("HISTORICAL INTRODUCTION", "ORIGINAL-LANGUAGE TEXT", "ENGLISH TEXT", "TEXTUAL NOTES", "SOURCES", "COPYRIGHT AND REUSE", "REMAINING UNCERTAINTIES")
FRONT_MATTER_FIELDS = {"id", "title", "alternate_titles", "attribution", "attribution_confidence", "original_language", "included_languages", "translation_author",
                       "translation_type", "tradition", "associated_churches", "regional_associations", "theological_themes", "devotional_focus", "spiritual_purpose",
                       "prayer_form", "occasions", "liturgical_season", "suggested_context", "duration_min_minutes", "duration_max_minutes", "duration_basis",
                       "research_status", "reuse_status", "ready_for_import"}
# The package's reuse labels, mapped to the application's license vocabulary. A new translation
# prepared for Optima Pars is the project's own work (not independently reviewed — stays proposed).
LICENSES = {"historical_public_domain": "public_domain", "public_domain_per_source": "public_domain"}
NEW_TRANSLATION = "public_domain_source_new_translation"


def parse_front_matter(lines: list[str]) -> dict:
    """The package's controlled YAML subset: scalars, quoted strings and string lists. Nothing else is accepted."""
    data, key = {}, None
    for raw in lines:
        if not raw.strip():
            continue
        if raw.startswith("  - ") and key is not None:
            data[key].append(_scalar(raw[4:].strip()))
        elif ":" in raw and not raw.startswith(" "):
            key, _, value = raw.partition(":")
            key, value = key.strip(), value.strip()
            data[key] = [] if value == "" else _scalar(value)
            key = key if value == "" else None
        else:
            raise ValueError(f"Unparseable front-matter line: {raw!r}")
    return data


def _scalar(value: str):
    if value.startswith('"') and value.endswith('"') and len(value) >= 2:
        return value[1:-1]
    if value in ("null", "~"):
        return None
    if value in ("true", "false"):
        return value == "true"
    if value == "[]":
        return []
    try:
        return float(value) if "." in value else int(value)
    except ValueError:
        return value


def parse_file(path: Path) -> tuple[dict, dict]:
    """Front matter and sections. UTF-8 is required; raises on any deviation from the stated format."""
    text_content = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    lines = text_content.split("\n")
    if lines[0].strip() != "---":
        raise ValueError("No YAML front matter opening")
    closing = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    front = parse_front_matter(lines[1:closing])
    sections, current = {}, None
    for line in lines[closing + 1:]:
        name = line.strip().rstrip(":")
        if line.strip().endswith(":") and name in SECTIONS:
            current, sections[name] = name, []
        elif current is not None:
            sections[current].append(line)
    return front, {name: "\n".join(body).strip("\n").strip() for name, body in sections.items()}


def normalize_title(value: str) -> str:
    cleaned = "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c))
    return " ".join("".join(c for c in cleaned.casefold() if c.isalnum() or c.isspace()).split())


def normalize_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def has_real_text(section: str | None) -> bool:
    return bool(section) and "NOT INCLUDED" not in section and "No Latin text included" not in section and not section.startswith("English-only")


@dataclass
class Candidate:
    manifest: dict
    front: dict = field(default_factory=dict)
    sections: dict = field(default_factory=dict)
    problems: list = field(default_factory=list)
    classification: str = ""
    matched: str | None = None
    note: str = ""

    @property
    def slug(self) -> str:
        return self.manifest["id"]

    @property
    def ready(self) -> bool:
        return self.manifest["ready_for_import"] == "true"


def load_package(package: Path) -> list[Candidate]:
    with (package / "manifest.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    candidates = [Candidate(manifest=row) for row in rows]
    seen = set()
    for candidate in candidates:
        row = candidate.manifest
        if row["id"] in seen:
            candidate.problems.append("duplicate id in manifest")
        seen.add(row["id"])
        path = package / row["filepath"]
        if not path.is_file():
            candidate.problems.append(f"file missing: {row['filepath']}")
            continue
        try:
            candidate.front, candidate.sections = parse_file(path)
        except (ValueError, UnicodeDecodeError, StopIteration) as exc:
            candidate.problems.append(f"unreadable: {exc}")
            continue
        candidate.problems.extend(validate(candidate))
    return candidates


def validate(candidate: Candidate) -> list[str]:
    front, row, problems = candidate.front, candidate.manifest, []
    if missing := FRONT_MATTER_FIELDS - set(front):
        problems.append(f"front matter missing: {sorted(missing)}")
    if front.get("id") != row["id"]:
        problems.append("front-matter id differs from manifest")
    if str(front.get("ready_for_import")).lower() != row["ready_for_import"]:
        problems.append("ready_for_import differs between file and manifest")
    try:
        low, high = float(row["duration_min_minutes"]), float(row["duration_max_minutes"])
        if not (0 < low <= high):
            problems.append("durations out of order")
    except ValueError:
        problems.append("durations are not numeric")
    if unknown := set(front.get("theological_themes") or []) - THEMES:
        problems.append(f"themes outside the controlled vocabulary: {sorted(unknown)}")
    if candidate.ready:
        if candidate.slug in NEVER_IMPORT:
            problems.append("marked ready but is a review-only entry")
        if not has_real_text(candidate.sections.get("ENGLISH TEXT")):
            problems.append("ready for import but has no English text")
        languages = [code for code in (front.get("included_languages") or []) if code != "en"]
        if languages and not has_real_text(candidate.sections.get("ORIGINAL-LANGUAGE TEXT")):
            problems.append(f"claims {languages} text but the original-language section is empty")
    return problems


def classify(candidates: list[Candidate], db) -> None:
    # Explicit columns only: the dry run must work against a database that predates newer columns.
    existing = {slug: identity for identity, slug in db.execute(select(Devotion.id, Devotion.slug))}
    titles_by_slug = {slug: title for slug, title in db.execute(select(Devotion.slug, Devotion.title))}
    by_title: dict[str, str] = {}
    for slug, title in titles_by_slug.items():
        by_title.setdefault(normalize_title(title), slug)
    texts: dict[str, dict[str, str]] = {}
    slug_of = {identity: slug for slug, identity in existing.items()}
    for devotion_id, language, body in db.execute(select(PrayerText.devotion_id, PrayerText.language, PrayerText.body)):
        texts.setdefault(slug_of[devotion_id], {})[language] = normalize_text(body or "")

    for candidate in candidates:
        if candidate.problems:
            candidate.classification = "INVALID"
            candidate.note = "; ".join(candidate.problems)
            continue
        if not candidate.ready:
            candidate.classification = "REVIEW_ONLY"
            candidate.note = "held for editorial review; never imported automatically"
            continue
        titles = [candidate.front.get("title") or ""] + list(candidate.front.get("alternate_titles") or [])
        matched = existing.get(candidate.slug) and candidate.slug
        title_hits = {by_title[normalize_title(t)] for t in titles if normalize_title(t) in by_title}
        if matched is None and len(title_hits) == 1:
            matched = title_hits.pop()
        elif matched is None and len(title_hits) > 1:
            candidate.classification, candidate.note = "AMBIGUOUS", f"title matches several existing devotions: {sorted(title_hits)}"
            continue
        if matched is None:
            candidate.classification = "NEW"
            continue
        candidate.matched = matched
        package_en = normalize_text(candidate.sections.get("ENGLISH TEXT") or "")
        existing_en = texts.get(matched, {}).get("en")
        if existing_en is not None and existing_en == package_en:
            candidate.classification, candidate.note = "EXISTING_IDENTICAL", "English wording matches the existing record"
        else:
            candidate.classification = "EXISTING_DIFFERENT"
            candidate.note = ("existing record has no English text to compare" if existing_en is None
                              else "English wording differs from the existing record") + "; not overwritten"


def build_devotion(candidate: Candidate) -> tuple[Devotion, list[PrayerText]]:
    front, sections, row = candidate.front, candidate.sections, candidate.manifest
    references = []
    for line in (sections.get("SOURCES") or "").split("\n"):
        line = line.strip()
        if line and line[0].isdigit():
            label = line.split(". ", 1)[-1][:280]
            url = next((w for w in line.split() if w.startswith("http")), None)
            references.append({"label": label, "url": url.rstrip(").,") if url else None})
    body = schemas.DevotionCreate(
        slug=candidate.slug, title=front["title"], category=(front.get("tradition") or "").split(";")[0].strip() or None,
        estimated_minutes=max(1, math.ceil(float(row["duration_max_minutes"]))),
        overview=sections.get("HISTORICAL INTRODUCTION") or front["title"],
        background=sections.get("TEXTUAL NOTES") or None,
        references=references, steps=[{"kind": "prayer", "text_slot": "main"}],
    )
    discovery = {key: front.get(key) for key in (
        "alternate_titles", "attribution", "attribution_confidence", "original_language", "included_languages", "translation_author", "translation_type", "tradition",
        "associated_churches", "regional_associations", "theological_themes", "devotional_focus", "spiritual_purpose", "prayer_form", "occasions", "liturgical_season",
        "suggested_context", "duration_min_minutes", "duration_max_minutes", "duration_basis", "research_status", "reuse_status")}
    discovery["source_file"] = row["filepath"]
    devotion = Devotion(**body.model_dump(), discovery=discovery, status="proposed", prose_origin="research_import", created_by=IMPORTED_BY)

    prayers = []
    original = [code for code in (front.get("included_languages") or []) if code != "en"]
    reuse = row["reuse_status"]
    if has_real_text(sections.get("ENGLISH TEXT")):
        prayers.append(PrayerText(
            slot="main", language="en", position=0, body=sections["ENGLISH TEXT"], is_translation=bool(original),
            translator=front.get("translation_author"), source_title=row["translation_source"],
            attribution=front.get("attribution"), license_status="permission_granted" if reuse == NEW_TRANSLATION else LICENSES.get(reuse, "unverified"),
            license_notes=sections.get("COPYRIGHT AND REUSE"), status="proposed", entered_by=IMPORTED_BY))
    if original and has_real_text(sections.get("ORIGINAL-LANGUAGE TEXT")):
        prayers.append(PrayerText(
            slot="main", language=original[0], position=0, body=sections["ORIGINAL-LANGUAGE TEXT"], is_translation=False,
            source_title=row["original_text_source"], attribution=front.get("attribution"),
            license_status=LICENSES.get(reuse, "public_domain" if reuse == NEW_TRANSLATION else "unverified"),
            license_notes=sections.get("COPYRIGHT AND REUSE"), status="proposed", entered_by=IMPORTED_BY))
    return devotion, prayers


def run(package: Path, session_factory, execute: bool) -> dict:
    candidates = load_package(package)
    counts = {"total": len(candidates), "ready": sum(c.ready for c in candidates), "review_only": sum(not c.ready for c in candidates)}
    with session_factory() as db:
        classify(candidates, db)
    if counts["total"] != EXPECTED_TOTAL or counts["ready"] != EXPECTED_READY:
        counts["warning"] = f"expected {EXPECTED_TOTAL} records with {EXPECTED_READY} ready; the files say {counts['total']}/{counts['ready']} — stopping before any write"
        execute = False
    report(candidates, counts)
    if not execute:
        counts["written"] = 0
        return counts
    with session_factory.begin() as db:
        written = 0
        for candidate in candidates:
            if candidate.classification != "NEW":
                continue
            devotion, prayers = build_devotion(candidate)
            db.add(devotion)
            db.flush()
            for prayer in prayers:
                prayer.devotion_id = devotion.id
                db.add(prayer)
            db.flush()
            record(db, devotion.id, IMPORTED_BY, "imported_draft", note=f"Devotion Library batch 01: {candidate.manifest['filepath']}")
            written += 1
        counts["written"] = written
    print(f"\nWrote {counts['written']} new devotions as unpublished 'proposed' drafts.")
    return counts


def report(candidates: list[Candidate], counts: dict) -> None:
    order = ("NEW", "EXISTING_IDENTICAL", "EXISTING_DIFFERENT", "AMBIGUOUS", "INVALID", "REVIEW_ONLY")
    print(f"Package: {counts['total']} records, {counts['ready']} marked ready, {counts['review_only']} review-only")
    if "warning" in counts:
        print(f"WARNING: {counts['warning']}")
    for kind in order:
        group = [c for c in candidates if c.classification == kind]
        counts[kind] = len(group)
        if not group:
            continue
        print(f"\n{kind} ({len(group)}):")
        for c in group:
            action = {"NEW": "would insert as proposed draft", "EXISTING_IDENTICAL": "skip", "EXISTING_DIFFERENT": "skip (never overwrites)",
                      "AMBIGUOUS": "skip (manual review)", "INVALID": "skip", "REVIEW_ONLY": "skip (editorial hold)"}[kind]
            matched = f" -> existing '{c.matched}'" if c.matched else ""
            print(f"  {c.slug}: {c.front.get('title', c.manifest['title'])}{matched} | {action}" + (f" | {c.note}" if c.note else ""))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--execute", action="store_true", help="write NEW entries as proposed drafts (default: dry run)")
    arguments = parser.parse_args(argv)
    settings = Settings()
    engine = make_engine(settings.database_url, settings.postgres_password.get_secret_value() if settings.postgres_password else None)
    try:
        with engine.connect() as connection:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        if arguments.execute and revision != HEAD_REVISION:
            print(f"Refusing to write: the database is at migration {revision}, not {HEAD_REVISION}. Apply migrations first (with approval).")
            return 2
        counts = run(arguments.package, make_session_factory(engine), arguments.execute)
    finally:
        engine.dispose()
    return 1 if counts.get("INVALID") or "warning" in counts else 0


if __name__ == "__main__":
    sys.exit(main())
