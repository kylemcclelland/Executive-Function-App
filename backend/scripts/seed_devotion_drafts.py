#!/usr/bin/env python
# ruff: noqa: E501
"""Create the ten foundational devotions as UNPUBLISHED editorial drafts, with their sourced prayer texts.

    export DATABASE_URL='postgresql+psycopg://...'                  # never on the command line
    python scripts/seed_devotion_drafts.py                           # dry run: shows exactly what it would do
    python scripts/seed_devotion_drafts.py --execute                 # apply it

What it guarantees
  * Idempotent. Run it twice and nothing is duplicated. A devotion that already exists (matched by its
    address) is left completely untouched: its status, approvals, text and edits are never overwritten.
    ``--add-missing-texts`` additionally adds a source text that does not yet exist for such a devotion; it
    still never changes anything that is there.
  * Everything starts as ``proposed``. No devotion or text is verified, approved or published, and the explanatory
    prose is marked as AI-drafted so the review screens label it unapproved.
  * It writes no prayer wording of its own. Wording comes only from seed_data/prayer_sources.json, where each text
    was copied programmatically from a cited source whose reproduction rights were checked. Where rights are not
    cleared the text is held as a citation with no wording.
  * It refuses a database that is not at the current migration, and a SQLite database that holds user data unless
    ``--allow-sqlite-with-user-data`` is passed deliberately (it only adds devotion rows). One transaction: all or nothing.
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE / "seed_data"))

import devotion_drafts  # noqa: E402
from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.db import make_engine, make_session_factory  # noqa: E402
from app.models import Devotion, PrayerText  # noqa: E402
from app.schemas import devotions as schemas  # noqa: E402
from app.services.devotions import record  # noqa: E402

MIN_REVISION = "0011"
ENTERED_BY = "seed:prayer-sources-v1"
SOURCES = HERE / "seed_data" / "prayer_sources.json"
USER_LATIN = HERE / "seed_data" / "user_supplied_latin.json"
ROSARY_DOCUMENT = HERE / "seed_data" / "rosary_document.json"
OWNER_TEXTS = HERE / "seed_data" / "owner_supplied_texts.json"


class Refused(Exception):
    pass


def load_drafts(codes: set[str] | None = None) -> list[dict]:
    """The drafts, validated by the same rules the editorial API applies to a new devotion.

    ``codes`` limits the run to some drafts (for example DEV-001 to DEV-006); reused prayers must then be among them.
    """
    if codes is not None and (unknown := codes - {d["code"] for d in devotion_drafts.DRAFTS}):
        raise Refused(f"Unknown draft code(s): {', '.join(sorted(unknown))}")
    checked = []
    for item in devotion_drafts.DRAFTS:
        if codes is not None and item["code"] not in codes:
            continue
        fields = {k: v for k, v in item.items() if k != "code"}
        model = schemas.DevotionCreate(**fields)
        checked.append({"code": item["code"], **model.model_dump()})
    slugs = [item["slug"] for item in checked]
    if len(set(slugs)) != len(slugs):
        raise Refused("Two drafts share an address")
    return checked


def normalization():
    """The authorized corrections applied to the user-supplied transcription (see seed_data/latin_normalization.py)."""
    import latin_normalization
    data = json.loads(USER_LATIN.read_text(encoding="utf-8"))
    return data, latin_normalization, latin_normalization.apply_all(data)


def user_supplied_texts() -> list[dict]:
    """The Latin prayers the owner supplied in a file, after the owner's authorized editorial normalization.

    The original verbatim transcription is kept untouched (user_supplied_latin.json) and its hash is checked before anything is
    applied. Rights are NOT established by the file, so they are recorded as unverified: the text can sit in the review queue but
    cannot be verified or approved until its source and rights have been recorded. A corrected spelling is never a verification.
    """
    if not USER_LATIN.exists():
        return []
    data, module, results = normalization()
    out = []
    for item in data["texts"]:
        result = results[item["devotion_slug"]]
        notes = [
            f"{data['provenance']}. Original file: {data['filename']} ({data['file_bytes']} bytes, SHA-256 {data['file_sha256']}). "
            f"Heading in the file: “{item['heading_in_file']}”, lines {item['lines_in_file']}.",
            f"Editorial normalization ({module.ID}) of the user-supplied transcription: only the corrections the owner authorized were applied: "
            f"{module.describe(result['counts'])}. No other wording was changed, translated or modernized. The before-and-after is in "
            "docs/latin-normalization-diff.md, where further proposed changes are listed for review and are NOT applied.",
            "The file contains no source reference, edition, translator or rights information, so none is recorded, and reproduction rights "
            "are not yet established.",
        ]
        if item["devotion_slug"] == "hail-mary":
            notes.append(f"Comma after “gratia plena”: {module.EDITION}")
        if item["observations"]:
            notes.append("Observations in the original transcription (the authorized ones are now corrected): " + "; ".join(item["observations"]) + ".")
        notes.append(f"Original verbatim transcription SHA-256 {result['original_sha256']}; stored wording SHA-256 {result['normalized_sha256']}.")
        out.append({
            "devotion_slug": item["devotion_slug"], "slot": item["slot"], "language": item["language"], "body": result["normalized"],
            "is_translation": False, "translator": None, "source_title": data["provenance"],
            "source_authority": "Supplied by the project owner; the file names no author or issuing authority",
            "source_edition": f"File: {data['filename']} (SHA-256 {data['file_sha256'][:16]}…), editorially normalized ({module.ID})",
            "source_date": None, "source_url": None,
            "attribution": f"{data['provenance']} (original file: {data['filename']}), with the owner's authorized normalization. The file names no author, edition or publisher.",
            "license_status": "unverified", "license_notes": "\n\n".join(notes), "source_retrieved_at": None,
        })
    return out


def earlier_wording(key: tuple) -> dict | None:
    """The cited source record already in prayer_sources.json for (devotion, slot, language), if any."""
    return next((t for t in json.loads(SOURCES.read_text(encoding="utf-8"))["texts"] if (t["devotion_slug"], t["slot"], t["language"]) == key), None)


def owner_supplied_texts() -> list[dict]:
    """Wording the owner typed in a message, stored exactly as given.

    The text comes only from seed_data/owner_supplied_texts.json. Where the owner says it replaces an earlier cited record, the
    earlier record is kept in prayer_sources.json (it is not deleted) and its wording hash is noted. Rights are unverified: a
    message names no source, so the text can sit in review but cannot be verified or approved until a source and rights are recorded.
    """
    if not OWNER_TEXTS.exists():
        return []
    data = json.loads(OWNER_TEXTS.read_text(encoding="utf-8"))
    out = []
    for item in data["texts"]:
        key = (item["devotion_slug"], item["slot"], item["language"])
        digest = hashlib.sha256(item["body"].encode("utf-8")).hexdigest()
        notes = [f"{data['provenance']}: {data['supplied_via']} on {data['supplied_on']}. The message names no author, translator, edition or rights information, "
                 "so none is recorded, and reproduction rights are not yet established. The wording is stored exactly as supplied."]
        old = earlier_wording(key) if item.get("supersedes_earlier_record") else None
        if old and old["body"]:
            notes.append(f"Replaces the earlier cited edition ({old['source_title']}, {old['source_date']}), whose different wording had SHA-256 "
                         f"{hashlib.sha256(old['body'].encode('utf-8')).hexdigest()}. That record is still in seed_data/prayer_sources.json.")
        notes.append(f"Stored wording SHA-256 {digest}.")
        out.append({
            "devotion_slug": item["devotion_slug"], "slot": item["slot"], "language": item["language"], "body": item["body"],
            "is_translation": False, "translator": None, "source_title": data["provenance"],
            "source_authority": "Supplied by the project owner; no author or issuing authority was named",
            "source_edition": f"{data['supplied_via']}, {data['supplied_on']}", "source_date": None, "source_url": None,
            "attribution": f"{data['provenance']} ({data['supplied_via'].lower()}, {data['supplied_on']}). No author, edition or publisher was named.",
            "license_status": "unverified", "license_notes": "\n\n".join(notes), "source_retrieved_at": None,
            "_replaces": bool(old and old["body"]),
        })
    return out


def apply_owner_supplied(db) -> dict:
    """Bring a text already in a database to the owner-supplied wording, safely.

    Only a text whose wording is still EXACTLY the earlier cited edition is replaced. It goes through the same edit path as any other
    edit, so every earlier verification and approval is discarded and the text returns to "proposed", and a log entry names the fields
    changed, never the wording. A text already holding the supplied wording is left alone; a text edited since is not touched at all.
    """
    from app.services.devotions import TEXT_CONTENT, apply_edit, text_fingerprint
    report = {"changed": [], "already": [], "skipped": []}
    for entry in owner_supplied_texts():
        slug = entry["devotion_slug"]
        devotion = db.scalar(select(Devotion).where(Devotion.slug == slug))
        row = next((t for t in devotion.texts if (t.slot, t.language) == (entry["slot"], entry["language"])), None) if devotion else None
        old = earlier_wording((slug, entry["slot"], entry["language"]))
        if row is None:
            report["skipped"].append((slug, "no text record yet (seeding creates it)"))
        elif row.body == entry["body"]:
            report["already"].append(slug)
        elif entry["_replaces"] and old and row.body == old["body"]:
            before = row.status
            values = {k: v for k, v in entry.items() if k in TEXT_CONTENT and k not in ("slot", "language")}
            changed = apply_edit(row, values, TEXT_CONTENT, text_fingerprint)
            record(db, devotion.id, OWNER_SUPPLIER, "text_updated", text_id=row.id, from_status=before, to_status=row.status, note=f"owner-supplied wording: {', '.join(changed)}")
            report["changed"].append((slug, before, row.status))
        else:
            report["skipped"].append((slug, "wording differs from the earlier edition (edited since); not touched"))
    return report


OWNER_SUPPLIER = "seed:owner-supplied-text"
COLLECTION_DEVOTION = "the-holy-rosary"
COLLECTION_PREFIX = "collection-"


def rosary_document_texts() -> list[dict]:
    """The ten prayers of the owner's document "The Prayers of the Rosary", verbatim, as a collection on the Holy Rosary devotion.

    Each prayer is stored in its own slot (collection-<prayer>), in the document's order, one English and one Latin text. They are held
    beside, never in place of, any wording another devotion already has: a slot that exists is never touched, and wording that differs from
    an existing edition is a separate edition for the reviewer to choose between. Rights are not established by the document, so they are
    recorded as unverified, and nothing is verified, approved or published. The document's own introductions are kept in the notes as source
    commentary, apart from the wording.
    """
    if not ROSARY_DOCUMENT.exists():
        return []
    data = json.loads(ROSARY_DOCUMENT.read_text(encoding="utf-8"))
    held = {(t["devotion_slug"], t["slot"], t["language"]): t["body"] for t in json.loads(SOURCES.read_text(encoding="utf-8"))["texts"] if t["body"]}
    out = []
    for position, prayer in enumerate(data["prayers"]):
        for language, field, title in (("en", "english", prayer["heading_in_file"].removeprefix("The ")), ("la", "latin", prayer["latin_title"])):
            body = prayer[field]
            notes = [
                f"{data['provenance']}. File: {data['filename']} ({data['file_bytes']} bytes, SHA-256 {data['file_sha256']}), prayer “{prayer['heading_in_file']}”, lines {prayer['lines_in_file'][0]}-{prayer['lines_in_file'][1]}. "
                "The wording is copied exactly; only the document's page numbers and its page-width line wraps were removed (verses and responses keep their own lines).",
                "The document states no author, translator, edition or rights information, so none is recorded and reproduction rights are not yet established.",
                f"Document's own introduction to this prayer (source commentary, not prayer text): {prayer['introduction']}",
            ]
            notes += [f"Document's own {line.split(':')[0].lower()} (source commentary, not prayer text): {line.split(': ', 1)[1] if line.startswith('Note:') else line}" for line in prayer["commentary_lines"]]
            related = prayer["related_devotion"]
            if related and (related, "main", language) in held and " ".join(held[(related, "main", language)].split()) != " ".join(body.split()):
                notes.append(f"Another edition of this prayer is held on the {related} devotion with different wording; both are kept for the reviewer to compare. Neither was changed.")
            notes.append(f"Stored wording SHA-256 {hashlib.sha256(body.encode('utf-8')).hexdigest()}.")
            out.append({
                "devotion_slug": COLLECTION_DEVOTION, "slot": COLLECTION_PREFIX + prayer["key"], "language": language, "body": body, "position": position,
                "title": title, "is_translation": False, "translator": None, "source_title": data["provenance"],
                "source_authority": "Supplied by the project owner; the document names no author or issuing authority",
                "source_edition": f"File: {data['filename']} (SHA-256 {data['file_sha256'][:16]}…)", "source_date": None, "source_url": None,
                "attribution": f"{data['provenance']} (file: {data['filename']}). The document names no author, edition or publisher.",
                "license_status": "unverified", "license_notes": "\n\n".join(notes), "source_retrieved_at": None,
            })
    return out


NORMALIZER = "seed:latin-normalization-v1"


def apply_latin_normalization(db) -> dict:
    """Bring Latin texts already in a database to the normalized wording, safely.

    Only a text whose wording is still EXACTLY the original verbatim import is changed. The change goes through the same edit path as any
    other, so every earlier verification and approval of that text is discarded and it returns to "proposed" (a corrected spelling is not a
    verification), and a log entry names the fields changed, never the wording. A text already normalized is left alone; a text that has
    been edited since the import is not touched at all. Reimporting the original file never undoes this: the importer only rewrites the
    original-transcription data file and never touches a database.
    """
    from app.services.devotions import TEXT_CONTENT, apply_edit, text_fingerprint
    _, _, results = normalization()
    entries = {e["devotion_slug"]: e for e in user_supplied_texts()}
    report = {"changed": [], "already": [], "skipped": []}
    for slug, entry in entries.items():
        devotion = db.scalar(select(Devotion).where(Devotion.slug == slug))
        row = next((t for t in devotion.texts if (t.slot, t.language) == ("main", "la")), None) if devotion else None
        if row is None:
            report["skipped"].append((slug, "no Latin text record"))
        elif row.body == entry["body"]:
            report["already"].append(slug)
        elif row.body == results[slug]["original"]:
            before = row.status
            changed = apply_edit(row, {"body": entry["body"], "license_notes": entry["license_notes"]}, TEXT_CONTENT, text_fingerprint)
            record(db, devotion.id, NORMALIZER, "text_updated", text_id=row.id, from_status=before, to_status=row.status, note=f"latin-normalization-v1: {', '.join(changed)}")
            report["changed"].append((slug, before, row.status))
        else:
            report["skipped"].append((slug, "wording differs from the original import (edited since); not touched"))
    return report


def merge_user_supplied(data: list[dict]) -> list[dict]:
    """A user-supplied text replaces an earlier citation-only record for the same prayer and language; it never replaces held wording."""
    supplied = user_supplied_texts()
    key = lambda t: (t["devotion_slug"], t["slot"], t["language"])  # noqa: E731
    earlier = {key(entry): entry for entry in data}
    for entry in supplied:
        old = earlier.get(key(entry))
        if old is not None and old["body"]:
            raise Refused(f"A user-supplied text would replace existing wording for {key(entry)}; refusing.")
        if old is not None:
            entry["license_notes"] += "\n\nReplaces the previously cited source record for this prayer (its wording was never held)."
    replaced = {key(entry) for entry in supplied}
    return [entry for entry in data if key(entry) not in replaced] + supplied


def load_texts(drafts: list[dict]) -> list[dict]:
    data = json.loads(SOURCES.read_text(encoding="utf-8"))["texts"]
    data = merge_user_supplied(data) + rosary_document_texts()
    supplied = owner_supplied_texts()
    replaced = {(t["devotion_slug"], t["slot"], t["language"]) for t in supplied if t["_replaces"]}
    data = [t for t in data if (t["devotion_slug"], t["slot"], t["language"]) not in replaced] + [{k: v for k, v in t.items() if k != "_replaces"} for t in supplied]
    known = {item["slug"] for item in drafts}
    every = {d["slug"] for d in devotion_drafts.DRAFTS}
    checked = []
    for item in data:
        if item["devotion_slug"] not in every:
            raise Refused(f"A source text belongs to an unknown devotion: {item['devotion_slug']}")
        if item["devotion_slug"] not in known:
            continue
        fields = {k: v for k, v in item.items() if k != "devotion_slug"}
        model = schemas.TextCreate(**fields)
        checked.append({"devotion_slug": item["devotion_slug"], **model.model_dump()})
    return checked


def check_target(engine, *, allow_user_data: bool = False) -> None:
    with engine.connect() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        if revision is None or revision < MIN_REVISION:
            raise Refused(f"The database is at migration {revision}, not {MIN_REVISION}: run the migrations first.")
        if engine.dialect.name == "sqlite" and not allow_user_data:
            users = connection.execute(text("SELECT count(*) FROM users")).scalar()
            if users:
                raise Refused("This SQLite database holds user data. By default it is never modified by this tool; use a scratch database, "
                              "or pass --allow-sqlite-with-user-data for your own local development database (take a backup first). The tool only adds devotion rows and never touches the user's data.")


def plan_and_apply(db, drafts: list[dict], texts: list[dict], *, add_missing_texts: bool) -> dict:
    report = {"devotions_created": [], "devotions_kept": [], "texts_created": [], "texts_kept": 0}
    for item in drafts:
        existing = db.scalar(select(Devotion).where(Devotion.slug == item["slug"]))
        wanted = [t for t in texts if t["devotion_slug"] == item["slug"]]
        if existing is not None:
            report["devotions_kept"].append(item["slug"])
            if not add_missing_texts:
                report["texts_kept"] += len(wanted)
                continue
            devotion = existing
        else:
            fields = {k: v for k, v in item.items() if k != "code"}
            devotion = Devotion(
                **fields, status="proposed", created_by=devotion_drafts.CREATED_BY,
                prose_origin=devotion_drafts.PROSE_ORIGIN,
            )
            db.add(devotion)
            db.flush()
            record(db, devotion.id, devotion_drafts.CREATED_BY, "seeded", to_status="proposed", note=item["code"])
            report["devotions_created"].append(item["slug"])
        have = {(t.slot, t.language) for t in devotion.texts}
        for entry in wanted:
            if (entry["slot"], entry["language"]) in have:
                report["texts_kept"] += 1
                continue
            fields = {k: v for k, v in entry.items() if k != "devotion_slug"}
            row = PrayerText(**fields, devotion=devotion, entered_by=ENTERED_BY)
            db.add(row)
            db.flush()
            record(db, devotion.id, ENTERED_BY, "text_created", text_id=row.id, to_status="proposed", note=f"{row.slot}/{row.language}")
            report["texts_created"].append((item["slug"], entry["slot"], entry["language"], bool(entry["body"])))
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--execute", action="store_true", help="apply the changes (the default only shows them)")
    parser.add_argument("--add-missing-texts", action="store_true", help="also add source texts missing from devotions that already exist")
    parser.add_argument("--url-env", default="DATABASE_URL", help="environment variable holding the database URL")
    parser.add_argument("--normalize-latin", action="store_true", help="bring already-seeded Latin texts that are still the original verbatim import to the authorized normalized wording (discards their verification and approval)")
    parser.add_argument("--allow-sqlite-with-user-data", action="store_true", help="permit a local SQLite database that holds user data (devotion rows are only added; nothing else is read or changed). Back it up first")
    parser.add_argument("--apply-owner-supplied", action="store_true", help="replace already-seeded texts that are still the earlier cited edition with the owner-supplied wording (discards their verification and approval)")
    parser.add_argument("--codes", help="only these drafts, comma-separated (for example DEV-001,DEV-002); the default is all ten")
    arguments = parser.parse_args(argv)
    url = os.environ.get(arguments.url_env, "")
    if not url:
        print(f"Set {arguments.url_env} to the database URL (it is not accepted on the command line).")
        return 2
    engine = None
    try:
        codes = {c.strip().upper() for c in arguments.codes.split(",") if c.strip()} if arguments.codes else None
        drafts = load_drafts(codes)
        texts = load_texts(drafts)
        engine = make_engine(url)
        parsed = make_url(url)
        print(f"Target: {parsed.get_backend_name()}://{parsed.host or ''}{parsed.database and '/' + parsed.database or ''}")
        check_target(engine, allow_user_data=arguments.allow_sqlite_with_user_data)
        with make_session_factory(engine)() as db:
            transaction = db.begin()
            try:
                report = plan_and_apply(db, drafts, texts, add_missing_texts=arguments.add_missing_texts)
                normalized = apply_latin_normalization(db) if arguments.normalize_latin else None
                owner = apply_owner_supplied(db) if arguments.apply_owner_supplied else None
            except BaseException:
                transaction.rollback()
                raise
            # A dry run does all the work and then rolls it back, so what it reports is exactly what would happen.
            transaction.commit() if arguments.execute else transaction.rollback()
    except Refused as refusal:
        print(f"STOP: {refusal}")
        return 1
    finally:
        if engine is not None:
            engine.dispose()
    verb = "Created" if arguments.execute else "Would create"
    print(f"{verb} {len(report['devotions_created'])} unpublished draft devotion(s): {', '.join(report['devotions_created']) or 'none'}")
    print(f"Left untouched (already present): {len(report['devotions_kept'])} devotion(s) {', '.join(report['devotions_kept'])}".rstrip())
    if normalized is not None:
        print(f"Latin normalization: {len(normalized['changed'])} {'changed' if arguments.execute else 'would change'} (returned to proposed), {len(normalized['already'])} already normalized, {len(normalized['skipped'])} skipped")
        for slug, why in normalized["skipped"]:
            print(f"  skipped {slug}: {why}")
    if owner is not None:
        print(f"Owner-supplied wording: {len(owner['changed'])} {'replaced' if arguments.execute else 'would be replaced'} (returned to proposed), {len(owner['already'])} already current, {len(owner['skipped'])} skipped")
        for slug, before, after in owner["changed"]:
            print(f"  {slug}: {before} -> {after}")
        for slug, why in owner["skipped"]:
            print(f"  skipped {slug}: {why}")
    with_wording = sum(1 for t in report["texts_created"] if t[3])
    print(f"{verb} {len(report['texts_created'])} proposed text record(s): {with_wording} with sourced wording, {len(report['texts_created']) - with_wording} citation-only (wording withheld)")
    if not arguments.execute:
        print("Dry run only: nothing was written. Re-run with --execute to apply.")
    else:
        print(f"Done at {datetime.now():%Y-%m-%d %H:%M}. Nothing was verified, approved or published.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
