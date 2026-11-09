"""Editorial rules for devotions: what may be shown, and how content earns its way to being shown.

Everything here exists to keep one promise: a prayer text reaches a reader only if a named human
entered it from a cited source, a named approver approved exactly those words, and nothing has
changed since. The application never writes, completes, paraphrases or translates prayer wording.

Three independent layers hold that line, so no single bug or shortcut opens it:
  1. the transition rules below (roles, order, and what a status requires);
  2. a content fingerprint stored at approval, re-checked every time a reader is served, so a change
     made any other way (a manual SQL edit, a future code path) stops the content being shown;
  3. CHECK constraints in the database that refuse an approved or published row with no approval.
"""

import hashlib
import json
from collections.abc import Callable
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import utcnow
from ..models import Devotion, DevotionEvent, PrayerText

DEVOTION_CONTENT = (
    "slug", "title", "subtitle", "category", "estimated_minutes", "overview", "background",
    "significance", "references", "instructions", "steps",
)
# Wording and its citation, together: changing either one must be approved again.
TEXT_CONTENT = (
    "slot", "language", "title", "body", "is_translation", "translator", "source_title",
    "source_edition", "source_url", "attribution", "license_status", "license_notes",
)

# (from, to) -> who may make the move. "either" means an editor or an approver.
TEXT_FLOW = {
    ("proposed", "source_verified"): "editor",
    ("source_verified", "pending_approval"): "editor",
    ("source_verified", "proposed"): "editor",
    ("pending_approval", "proposed"): "either",
    ("pending_approval", "approved"): "approver",
    ("approved", "proposed"): "approver",
}
DEVOTION_FLOW = {
    **TEXT_FLOW,
    ("approved", "published"): "approver",
    ("published", "approved"): "approver",
    ("published", "proposed"): "approver",
}
# Moving into one of these needs the content to be complete.
GUARDED = {"source_verified", "pending_approval", "approved", "published"}


def fingerprint(entity, fields: tuple[str, ...]) -> str:
    payload = {name: getattr(entity, name) for name in fields}
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def devotion_fingerprint(devotion: Devotion) -> str:
    return fingerprint(devotion, DEVOTION_CONTENT)


def text_fingerprint(text: PrayerText) -> str:
    return fingerprint(text, TEXT_CONTENT)


def text_problems(text: PrayerText) -> list[str]:
    """Why this wording cannot yet be called verified: a prayer needs an attributable source."""
    problems = []
    if not text.source_title:
        problems.append("Name the source of this wording (title of the book or document)")
    if not text.attribution:
        problems.append("Add the attribution line to be shown with the text")
    if text.license_status == "unverified":
        problems.append("Record whether the wording is public domain, licensed or permitted")
    if text.is_translation and not text.translator:
        problems.append("Name the translator")
    return problems


def devotion_problems(devotion: Devotion) -> list[str]:
    problems = []
    if (devotion.background or devotion.significance) and not devotion.references:
        problems.append("Cite at least one source for the background or spiritual significance")
    wanted = {step["text_slot"] for step in devotion.steps if step.get("text_slot")}
    if missing := sorted(wanted - {text.slot for text in devotion.texts}):
        problems.append(f"Steps use prayer text slots that have no text yet: {', '.join(missing)}")
    return problems


# ---- Visibility: the only gate between stored content and a reader ----------------------------
def text_is_public(text: PrayerText) -> bool:
    return (
        text.status == "approved" and bool(text.approved_by)
        and text.approved_hash == text_fingerprint(text)
    )


def devotion_is_public(devotion: Devotion) -> bool:
    return (
        devotion.status == "published" and devotion.published_at is not None
        and bool(devotion.approved_by) and devotion.approved_hash == devotion_fingerprint(devotion)
    )


def public_texts(devotion: Devotion) -> list[PrayerText]:
    return [text for text in devotion.texts if text_is_public(text)]


def published_devotions(db: Session) -> list[Devotion]:
    rows = db.scalars(
        select(Devotion).where(Devotion.status == "published").order_by(Devotion.title)
    ).all()
    return [devotion for devotion in rows if devotion_is_public(devotion)]


def published_devotion(db: Session, slug: str) -> Devotion:
    devotion = db.scalar(select(Devotion).where(Devotion.slug == slug))
    # The same answer for "missing" and "not approved": a reader cannot probe for drafts.
    if devotion is None or not devotion_is_public(devotion):
        raise HTTPException(404, "Devotion not found")
    return devotion


def reader_text(text: PrayerText) -> dict:
    return {
        "id": text.id, "slot": text.slot, "language": text.language, "title": text.title,
        "body": text.body,
        "source": {
            "title": text.source_title, "edition": text.source_edition,
            "translator": text.translator, "is_translation": text.is_translation,
            "attribution": text.attribution, "url": text.source_url,
            "license_status": text.license_status,
        },
    }


def reader_brief(devotion: Devotion, bookmarked: bool) -> dict:
    return {
        "id": devotion.id, "slug": devotion.slug, "title": devotion.title,
        "subtitle": devotion.subtitle, "category": devotion.category,
        "estimated_minutes": devotion.estimated_minutes, "bookmarked": bookmarked,
        "has_text": bool(public_texts(devotion)),
    }


def reader_detail(devotion: Devotion, bookmarked: bool) -> dict:
    return {
        **reader_brief(devotion, bookmarked), "overview": devotion.overview,
        "background": devotion.background, "significance": devotion.significance,
        "references": devotion.references, "instructions": devotion.instructions,
        "steps": devotion.steps, "texts": [reader_text(t) for t in public_texts(devotion)],
    }


# ---- Editorial views --------------------------------------------------------------------------
def editorial_text(text: PrayerText) -> dict:
    values = {
        name: getattr(text, name) for name in (
            "id", "slot", "language", "position", "title", "body", "is_translation", "translator",
            "source_title", "source_edition", "source_url", "attribution", "license_status",
            "license_notes", "status", "entered_by", "source_verified_by", "source_verified_at",
            "approved_by", "approved_at", "updated_at",
        )
    }
    return {**values, "approval_current": text_is_public(text), "problems": text_problems(text)}


def editorial_devotion(devotion: Devotion) -> dict:
    values = {
        name: getattr(devotion, name) for name in (
            "id", "slug", "title", "subtitle", "category", "estimated_minutes", "overview",
            "background", "significance", "references", "instructions", "steps", "status",
            "created_by", "source_verified_by", "source_verified_at", "approved_by", "approved_at",
            "published_at", "updated_at",
        )
    }
    return {
        **values,
        "approval_current": devotion_is_public(devotion),
        "problems": devotion_problems(devotion),
        "texts": [editorial_text(text) for text in devotion.texts],
    }


# ---- Changes ----------------------------------------------------------------------------------
def record(
    db: Session, devotion_id: UUID, actor: str, action: str, *, text_id: UUID | None = None,
    from_status: str | None = None, to_status: str | None = None, note: str | None = None,
) -> None:
    db.add(DevotionEvent(
        devotion_id=devotion_id, text_id=text_id, actor=actor, action=action,
        from_status=from_status, to_status=to_status, note=note,
    ))


def reset_approvals(entity) -> None:
    entity.status = "proposed"
    entity.source_verified_by = entity.source_verified_at = None
    entity.approved_by = entity.approved_at = entity.approved_hash = None
    if hasattr(entity, "published_at"):
        entity.published_at = None


def apply_edit(
    entity, values: dict, fields: tuple[str, ...], fingerprint_of: Callable,
) -> list[str]:
    """Set ``values``; if the approvable content really changed, discard every earlier sign-off.

    Returns the names of the changed fields (never their values: prayer wording is not copied
    into logs). A save that changes nothing leaves the sign-offs alone.
    """
    before = fingerprint_of(entity)
    changed = []
    for name, value in values.items():
        if name in fields and getattr(entity, name) != value:
            changed.append(name)
        setattr(entity, name, value)
    if fingerprint_of(entity) != before:
        reset_approvals(entity)
    return changed


def _allowed(role: str, actor) -> bool:
    return {
        "editor": actor.is_editor, "approver": actor.is_approver,
        "either": actor.is_editor or actor.is_approver,
    }[role]


def transition(
    db: Session, entity: Devotion | PrayerText, target: str, actor, note: str | None,
) -> None:
    """Move ``entity`` one step along the workflow, enforcing role, order and completeness."""
    is_devotion = isinstance(entity, Devotion)
    flow = DEVOTION_FLOW if is_devotion else TEXT_FLOW
    current = entity.status
    required = flow.get((current, target))
    if required is None:
        raise HTTPException(409, f"A {'devotion' if is_devotion else 'prayer text'} cannot move "
                                 f"from {current} to {target}")
    if not _allowed(required, actor):
        raise HTTPException(403, f"The {required} role is required for this step")
    if target in GUARDED:
        problems = devotion_problems(entity) if is_devotion else text_problems(entity)
        if problems:
            raise HTTPException(409, "; ".join(problems))
    now = utcnow()
    if target == "proposed":
        reset_approvals(entity)
    elif target == "source_verified":
        entity.source_verified_by, entity.source_verified_at = actor.clerk_user_id, now
    elif target == "approved":
        if current == "published":
            entity.published_at = None
        else:
            fingerprint_now = (devotion_fingerprint if is_devotion else text_fingerprint)(entity)
            entity.approved_by, entity.approved_at = actor.clerk_user_id, now
            entity.approved_hash = fingerprint_now
    elif target == "published":
        if entity.approved_hash != devotion_fingerprint(entity):
            raise HTTPException(409, "The devotion changed after it was approved")
        entity.published_at = now
    entity.status = target
    devotion_id = entity.id if is_devotion else entity.devotion_id
    record(
        db, devotion_id, actor.clerk_user_id, "transition",
        text_id=None if is_devotion else entity.id, from_status=current, to_status=target,
        note=note,
    )
