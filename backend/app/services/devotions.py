"""Editorial rules for devotions: what may be shown, and how content earns its way to being shown.

Everything here exists to keep one promise: a prayer text reaches a reader only if its exact wording
came from a cited source whose terms permit reproducing it, a named approver approved exactly those
words, and nothing has changed since. The application never writes, completes, paraphrases or
translates prayer wording.

Three independent layers hold that line, so no single bug or shortcut opens it:
  1. the transition rules below (roles, order, and what a status requires);
  2. a content fingerprint stored at approval, re-checked every time a reader is served, so a change
     made any other way (a manual SQL edit, a future code path) stops the content being shown;
  3. CHECK constraints in the database that refuse an approved or published row with no approval,
     and any state past "proposed" for a text with no wording, no source or uncleared rights.
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
    "significance", "references", "instructions", "steps", "choice_label",
)
# Wording and everything known about where it came from, together: changing any of it must be
# approved again.
TEXT_CONTENT = (
    "slot", "language", "title", "body", "is_translation", "translator", "source_title",
    "source_authority", "source_edition", "source_date", "source_url", "source_retrieved_at",
    "attribution", "license_status", "license_notes",
)
# Rights that allow the wording to be republished. "restricted" and "unverified" do not.
RIGHTS_CLEARED = {"public_domain", "licensed", "permission_granted"}

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

# A named decision is only valid for particular moves. "reject_text" may also be recorded on a text
# that is still only a proposal (it stays "proposed"; the reason goes in the log).
DECISIONS = {
    "return_for_research": {("source_verified", "proposed"), ("pending_approval", "proposed")},
    "reject_text": {
        ("proposed", "proposed"), ("source_verified", "proposed"), ("pending_approval", "proposed"),
    },
    "reject_approval": {("pending_approval", "proposed")},
    "withdraw": {("approved", "proposed"), ("published", "proposed")},
}


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


def text_problems(text: PrayerText) -> list[str]:
    """Why this wording cannot yet be called verified: it needs wording, a source and rights."""
    problems = []
    if not has_body(text):
        problems.append(
            "No wording is held for this text, so it cannot be verified or approved "
            "(obtain it from a source whose terms permit reproduction)"
        )
    if not text.source_title:
        problems.append("Name the source of this wording (title of the book or document)")
    if not text.attribution:
        problems.append("Add the attribution line to be shown with the text")
    if text.license_status == "unverified":
        problems.append("Record whether the wording is public domain, licensed or permitted")
    elif text.license_status == "restricted":
        problems.append(
            "Reproduction rights are not cleared: the wording may be cited and linked, "
            "not republished"
        )
    if text.is_translation and not text.translator:
        problems.append("Name the translator")
    return problems


def _owner_slug(step: dict, devotion: Devotion) -> str:
    return step.get("devotion_slug") or devotion.slug


def devotion_problems(devotion: Devotion, db: Session | None = None) -> list[str]:
    problems = []
    if (devotion.background or devotion.significance) and not devotion.references:
        problems.append("Cite at least one source for the background or spiritual significance")
    own = {text.slot for text in devotion.texts}
    wanted = {
        step["text_slot"] for step in devotion.steps
        if step.get("text_slot") and _owner_slug(step, devotion) == devotion.slug
        and not step.get("optional")
    }
    if missing := sorted(wanted - own):
        problems.append(f"Steps use prayer text slots that have no text yet: {', '.join(missing)}")
    if db is not None:
        for slug, slot in sorted({
            (step["devotion_slug"], step["text_slot"]) for step in devotion.steps
            if step.get("devotion_slug") and step["devotion_slug"] != devotion.slug
            and step.get("text_slot")
        }):
            other = db.scalar(select(Devotion).where(Devotion.slug == slug))
            if other is None:
                problems.append(
                    f"A step reuses a prayer from a devotion that does not exist: {slug}"
                )
            elif slot not in {text.slot for text in other.texts}:
                problems.append(f"A step reuses {slug}/{slot}, which has no such prayer text")
    return problems


# ---- Visibility: the only gate between stored content and a reader ----------------------------
def text_is_public(text: PrayerText) -> bool:
    return (
        text.status == "approved" and bool(text.approved_by) and has_body(text)
        and text.license_status in RIGHTS_CLEARED
        and text.approved_hash == text_fingerprint(text)
    )


def devotion_is_public(devotion: Devotion) -> bool:
    return (
        devotion.status == "published" and devotion.published_at is not None
        and bool(devotion.approved_by) and devotion.approved_hash == devotion_fingerprint(devotion)
    )


def public_texts(devotion: Devotion) -> list[PrayerText]:
    return [text for text in devotion.texts if text_is_public(text)]


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
    """What a reader may see for this devotion: its own approved texts, plus the approved texts of
    published devotions whose prayers its steps reuse. Nothing else is ever included."""
    found = [(devotion, text) for text in public_texts(devotion)]
    wanted = {
        (step["devotion_slug"], step["text_slot"]) for step in devotion.steps
        if step.get("devotion_slug") and step["devotion_slug"] != devotion.slug
        and step.get("text_slot")
    }
    for slug, other in referenced_devotions(devotion, db).items():
        if not devotion_is_public(other):
            continue
        found.extend((other, text) for text in public_texts(other) if (slug, text.slot) in wanted)
    return found


def publication_problems(devotion: Devotion, db: Session, *, approved: bool = False) -> list[str]:
    """Everything that stops this devotion being published, in plain words.

    A devotion may be published with one language approved (English alone, say). It may not be
    published with nothing a reader could pray, or with a step whose prayer has no approved wording.
    """
    problems = []
    if not approved and devotion.status not in {"approved", "published"}:
        problems.append("The devotion itself has not been approved yet")
    visible = {(owner.slug, text.slot) for owner, text in available_texts(devotion, db)}
    if not visible:
        problems.append("No prayer text is approved yet: approve at least one (English or Latin)")
    others = referenced_devotions(devotion, db)
    # One line per unmet prayer, however many steps use it (the Rosary reuses one dozens of times).
    unmet: dict[tuple[str, str, str], list[int]] = {}
    for number, step in enumerate(devotion.steps, 1):
        slot, owner = step.get("text_slot"), _owner_slug(step, devotion)
        if not slot or step.get("optional") or (owner, slot) in visible:
            continue
        outside = owner != devotion.slug
        kind = "unpublished" if outside and (
            owner not in others or not devotion_is_public(others[owner])
        ) else "unapproved"
        unmet.setdefault((kind, owner, slot), []).append(number)
    for (kind, owner, slot), numbers in unmet.items():
        subject, plural = _steps_phrase(numbers)
        if kind == "unpublished":
            verb = "reuse" if plural else "reuses"
            problems.append(
                f"{subject} {verb} {owner}/{slot}, but that devotion is not published yet"
            )
        else:
            verb = "need" if plural else "needs"
            problems.append(f"{subject} {verb} an approved text for {owner}/{slot}")
    return problems


def _steps_phrase(numbers: list[int]) -> tuple[str, bool]:
    """"Step 3", "Steps 3, 7 and 12" or "27 steps (from step 3)": short however many steps."""
    if len(numbers) == 1:
        return f"Step {numbers[0]}", False
    if len(numbers) <= 4:
        return f"Steps {', '.join(map(str, numbers[:-1]))} and {numbers[-1]}", True
    return f"{len(numbers)} steps (from step {numbers[0]})", True


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
        "body": text.body, "devotion_slug": owner.slug, "source": _source(text),
    }


def reader_brief(devotion: Devotion, bookmarked: bool, db: Session) -> dict:
    return {
        "id": devotion.id, "slug": devotion.slug, "title": devotion.title,
        "subtitle": devotion.subtitle, "category": devotion.category,
        "estimated_minutes": devotion.estimated_minutes, "bookmarked": bookmarked,
        "has_text": bool(available_texts(devotion, db)),
    }


def _detail(devotion: Devotion, bookmarked: bool, db: Session, texts: list[dict]) -> dict:
    return {
        **reader_brief(devotion, bookmarked, db), "overview": devotion.overview,
        "background": devotion.background, "significance": devotion.significance,
        "references": devotion.references, "instructions": devotion.instructions,
        "steps": devotion.steps, "choice_label": devotion.choice_label, "texts": texts,
    }


def reader_detail(devotion: Devotion, bookmarked: bool, db: Session) -> dict:
    texts = [reader_text(text, owner) for owner, text in available_texts(devotion, db)]
    return _detail(devotion, bookmarked, db, texts)


def preview_detail(devotion: Devotion, db: Session) -> dict:
    """The page as the Oratory would render it, with unapproved texts included and marked.

    Editors only. Each text says whether a reader would see it right now, so a preview can never be
    mistaken for what is published.
    """
    owners = {devotion.slug: devotion, **referenced_devotions(devotion, db)}
    wanted = {
        (step.get("devotion_slug") or devotion.slug, step["text_slot"])
        for step in devotion.steps if step.get("text_slot")
    }
    texts = []
    for slug, owner in owners.items():
        for text in owner.texts:
            if slug == devotion.slug or (slug, text.slot) in wanted:
                texts.append({
                    **reader_text(text, owner), "status": text.status,
                    "approval_current": text_is_public(text),
                    "publicly_visible": text_is_public(text) and devotion_is_public(owner),
                    "has_body": has_body(text),
                    "rights_cleared": text.license_status in RIGHTS_CLEARED,
                    "license_notes": text.license_notes,
                })
    return {
        **_detail(devotion, False, db, texts), "devotion_status": devotion.status,
        "prose_origin": devotion.prose_origin,
        "has_text": any(item["has_body"] for item in texts),
    }


# ---- Editorial views --------------------------------------------------------------------------
def events_for(db: Session, devotion_id: UUID) -> list[DevotionEvent]:
    return list(db.scalars(
        select(DevotionEvent).where(DevotionEvent.devotion_id == devotion_id)
        .order_by(DevotionEvent.created_at, DevotionEvent.id)
    ))


def editorial_text(text: PrayerText, owner: Devotion, events: list[DevotionEvent]) -> dict:
    values = {
        name: getattr(text, name) for name in (
            "id", "slot", "language", "position", "title", "body", "is_translation", "translator",
            "source_title", "source_authority", "source_edition", "source_date", "source_url",
            "source_retrieved_at", "attribution", "license_status", "license_notes", "status",
            "entered_by", "source_verified_by", "source_verified_at", "approved_by", "approved_at",
            "updated_at",
        )
    }
    latest = next((event for event in reversed(events) if event.text_id == text.id), None)
    return {
        **values, "devotion_slug": owner.slug, "has_body": has_body(text),
        "rights_cleared": text.license_status in RIGHTS_CLEARED,
        "approval_current": text_is_public(text), "problems": text_problems(text),
        "last_event": latest,
    }


def editorial_devotion(devotion: Devotion, db: Session) -> dict:
    values = {
        name: getattr(devotion, name) for name in (
            "id", "slug", "title", "subtitle", "category", "estimated_minutes", "overview",
            "background", "significance", "references", "instructions", "steps", "choice_label",
            "prose_origin", "status", "created_by", "source_verified_by", "source_verified_at",
            "approved_by", "approved_at", "published_at", "updated_at",
        )
    }
    events = events_for(db, devotion.id)
    return {
        **values,
        "approval_current": devotion_is_public(devotion),
        "problems": devotion_problems(devotion, db),
        "publication_problems": publication_problems(devotion, db),
        "texts": [editorial_text(text, devotion, events) for text in devotion.texts],
    }


def editorial_brief(devotion: Devotion) -> dict:
    return {
        "id": devotion.id, "slug": devotion.slug, "title": devotion.title,
        "category": devotion.category, "status": devotion.status,
        "prose_origin": devotion.prose_origin,
        "texts": [{
            "slot": text.slot, "language": text.language, "status": text.status,
            "license_status": text.license_status, "has_body": has_body(text),
            "source_verified": text.source_verified_at is not None,
        } for text in devotion.texts],
        "texts_approved": sum(text.status == "approved" for text in devotion.texts),
        "texts_total": len(devotion.texts), "updated_at": devotion.updated_at,
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
    decision: str | None = None,
) -> None:
    """Move ``entity`` one step along the workflow, enforcing role, order and completeness."""
    is_devotion = isinstance(entity, Devotion)
    flow = DEVOTION_FLOW if is_devotion else TEXT_FLOW
    current = entity.status
    if decision is not None and (current, target) not in DECISIONS[decision]:
        raise HTTPException(
            409, f"'{decision}' does not apply to a move from {current} to {target}",
        )
    stays = decision == "reject_text" and current == target == "proposed"
    required = "either" if stays else flow.get((current, target))
    if required is None:
        raise HTTPException(409, f"A {'devotion' if is_devotion else 'prayer text'} cannot move "
                                 f"from {current} to {target}")
    if decision == "reject_approval":
        required = "approver"  # turning down what an editor submitted is the approver's call
    if not _allowed(required, actor):
        raise HTTPException(403, f"The {required} role is required for this step")
    if target in GUARDED:
        problems = devotion_problems(entity, db) if is_devotion else text_problems(entity)
        if problems:
            raise HTTPException(409, "; ".join(problems))
        if target == "published":
            if blockers := publication_problems(entity, db, approved=True):
                raise HTTPException(409, "; ".join(blockers))
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
        db, devotion_id, actor.clerk_user_id, decision or "transition",
        text_id=None if is_devotion else entity.id, from_status=current, to_status=target,
        note=note,
    )
