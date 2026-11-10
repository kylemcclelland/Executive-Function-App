"""The devotion library: prayers and devotions the owner keeps for personal use.

Everything stored is shown. There is no approval or publication step: a devotion and every
prayer text recorded for it is readable in The Oratory. The application never writes, completes,
paraphrases or translates prayer wording; wording enters only through the seeding scripts,
copied exactly from a supplied or cited source, and each text keeps its source and rights
information. A record that holds only a citation (no wording, because rights were not cleared or
the text was not supplied) is kept and shown as such.

The older editorial workflow (statuses, approvals, publication) is retired. Its columns remain
in the database as history and are no longer read or required. ``apply_edit`` and ``record``
remain for the seeding scripts' safe in-place corrections.
"""

import hashlib
import json
from collections.abc import Callable
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Devotion, DevotionEvent, PrayerText

DEVOTION_CONTENT = (
    "slug", "title", "subtitle", "category", "estimated_minutes", "overview", "background",
    "significance", "references", "instructions", "steps", "choice_label",
)
# Wording and everything known about where it came from, together.
TEXT_CONTENT = (
    "slot", "language", "title", "body", "is_translation", "translator", "source_title",
    "source_authority", "source_edition", "source_date", "source_url", "source_retrieved_at",
    "attribution", "license_status", "license_notes",
)


def fingerprint(entity, fields: tuple[str, ...]) -> str:
    payload = {name: getattr(entity, name) for name in fields}
    text = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str,
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def devotion_fingerprint(devotion: Devotion) -> str:
    return fingerprint(devotion, DEVOTION_CONTENT)


def text_fingerprint(text: PrayerText) -> str:
    return fingerprint(text, TEXT_CONTENT)


def has_body(text: PrayerText) -> bool:
    return bool(text.body and text.body.strip())


# ---- What the library shows --------------------------------------------------------------------
def library_devotions(db: Session) -> list[Devotion]:
    return list(db.scalars(select(Devotion).order_by(Devotion.title)))


def library_devotion(db: Session, slug: str) -> Devotion:
    devotion = db.scalar(select(Devotion).where(Devotion.slug == slug))
    if devotion is None:
        raise HTTPException(404, "Devotion not found")
    return devotion


def referenced_devotions(devotion: Devotion, db: Session) -> dict[str, Devotion]:
    """The other devotions whose prayers this one's steps reuse (one level; never recursive)."""
    slugs = {
        step["devotion_slug"] for step in devotion.steps
        if step.get("devotion_slug") and step["devotion_slug"] != devotion.slug
    }
    if not slugs:
        return {}
    rows = db.scalars(select(Devotion).where(Devotion.slug.in_(slugs))).all()
    return {row.slug: row for row in rows}


def available_texts(devotion: Devotion, db: Session) -> list[tuple[Devotion, PrayerText]]:
    """This devotion's own texts, plus those of other devotions whose prayers its steps reuse."""
    found = [(devotion, text) for text in devotion.texts]
    wanted = {
        (step["devotion_slug"], step["text_slot"]) for step in devotion.steps
        if step.get("devotion_slug") and step["devotion_slug"] != devotion.slug
        and step.get("text_slot")
    }
    for slug, other in referenced_devotions(devotion, db).items():
        found.extend((other, text) for text in other.texts if (slug, text.slot) in wanted)
    return found


def _source(text: PrayerText) -> dict:
    return {
        "title": text.source_title, "authority": text.source_authority,
        "edition": text.source_edition, "date": text.source_date,
        "translator": text.translator, "is_translation": text.is_translation,
        "attribution": text.attribution, "url": text.source_url,
        "license_status": text.license_status,
    }


def reader_text(text: PrayerText, owner: Devotion) -> dict:
    return {
        "id": text.id, "slot": text.slot, "language": text.language, "title": text.title,
        "body": text.body, "has_wording": has_body(text), "devotion_slug": owner.slug,
        "source": _source(text),
    }


def reader_brief(devotion: Devotion, bookmarked: bool, db: Session) -> dict:
    return {
        "id": devotion.id, "slug": devotion.slug, "title": devotion.title,
        "subtitle": devotion.subtitle, "category": devotion.category,
        "estimated_minutes": devotion.estimated_minutes, "bookmarked": bookmarked,
        "has_text": any(has_body(text) for _, text in available_texts(devotion, db)),
    }


def reader_detail(devotion: Devotion, bookmarked: bool, db: Session) -> dict:
    texts = [reader_text(text, owner) for owner, text in available_texts(devotion, db)]
    return {
        **reader_brief(devotion, bookmarked, db), "overview": devotion.overview,
        "background": devotion.background, "significance": devotion.significance,
        "references": devotion.references, "instructions": devotion.instructions,
        "steps": devotion.steps, "choice_label": devotion.choice_label, "texts": texts,
    }


# ---- Changes (used by the seeding scripts) -------------------------------------------------------
def record(
    db: Session, devotion_id: UUID, actor: str, action: str, *, text_id: UUID | None = None,
    from_status: str | None = None, to_status: str | None = None, note: str | None = None,
) -> None:
    db.add(DevotionEvent(
        devotion_id=devotion_id, text_id=text_id, actor=actor, action=action,
        from_status=from_status, to_status=to_status, note=note,
    ))


def reset_approvals(entity) -> None:
    """Return a record to its starting state when its content changes (history columns only)."""
    entity.status = "proposed"
    entity.source_verified_by = entity.source_verified_at = None
    entity.approved_by = entity.approved_at = entity.approved_hash = None
    if hasattr(entity, "published_at"):
        entity.published_at = None


def apply_edit(
    entity, values: dict, fields: tuple[str, ...], fingerprint_of: Callable,
) -> list[str]:
    """Set ``values``; return the changed field names (never values: wording is not logged)."""
    before = fingerprint_of(entity)
    changed = []
    for name, value in values.items():
        if name in fields and getattr(entity, name) != value:
            changed.append(name)
        setattr(entity, name, value)
    if fingerprint_of(entity) != before:
        reset_approvals(entity)
    return changed
