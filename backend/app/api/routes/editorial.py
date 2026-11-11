# ruff: noqa: E501
"""The owner's editorial dashboard API: review, verify, approve and publish devotion drafts.

Every route requires the one configured owner (``OWNER_CLERK_USER_ID``); any other account —
signed in or not — gets 403/401 and never sees an unpublished draft, its texts or its history.
Transitions follow the schema's own editorial constraints (proposed → source_verified →
approved → published for a devotion; texts are approved, never published), every action is
recorded as a DevotionEvent with the owner as actor, and nothing ever happens automatically:
publication is one explicit owner action per devotion, after its texts are approved.
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from ...db import utcnow
from ...models import Devotion, DevotionEvent, PrayerText
from ...services import devotions as svc
from ..dependencies import DB, Owner

router = APIRouter(prefix="/api/editorial", tags=["editorial"])

DEVOTION_FLOW = {"verify-source": ("proposed", "source_verified"), "approve": ("source_verified", "approved"), "publish": ("approved", "published")}
TEXT_FLOW = {"verify-source": ("proposed", "source_verified"), "approve": ("source_verified", "approved")}


def owned_draft(db, slug: str) -> Devotion:
    devotion = db.scalar(select(Devotion).where(Devotion.slug == slug))
    if devotion is None:
        raise HTTPException(404, "Devotion not found")
    return devotion


def text_out(text: PrayerText) -> dict:
    return {"id": str(text.id), "slot": text.slot, "language": text.language, "title": text.title, "body": text.body, "status": text.status,
            "is_translation": text.is_translation, "translator": text.translator, "source_title": text.source_title, "source_url": text.source_url,
            "attribution": text.attribution, "license_status": text.license_status, "license_notes": text.license_notes}


def brief(devotion: Devotion) -> dict:
    return {"slug": devotion.slug, "title": devotion.title, "status": devotion.status, "category": devotion.category,
            "estimated_minutes": devotion.estimated_minutes, "languages": sorted({t.language for t in devotion.texts}),
            "discovery": devotion.discovery, "created_by": devotion.created_by, "prose_origin": devotion.prose_origin,
            "published": devotion.status == "published", "updated_at": devotion.updated_at,
            "attribution": (devotion.discovery or {}).get("attribution"),
            "themes": (devotion.discovery or {}).get("theological_themes") or [],
            "tradition": (devotion.discovery or {}).get("tradition") or devotion.category}


@router.get("/access")
def editorial_access(user: Owner):
    """A light probe the frontend uses to decide whether to show the dashboard at all. Non-owners get 403 and no data."""
    return {"owner": True}


@router.get("/devotions")
def editorial_queue(db: DB, user: Owner):
    devotions = db.scalars(select(Devotion).order_by(Devotion.title)).all()
    summary = {"total": len(devotions)}
    for devotion in devotions:
        summary[devotion.status] = summary.get(devotion.status, 0) + 1
    return {"summary": summary, "devotions": [brief(d) for d in devotions]}


@router.get("/devotions/{slug}")
def editorial_detail(slug: str, db: DB, user: Owner):
    devotion = owned_draft(db, slug)
    events = db.scalars(select(DevotionEvent).where(DevotionEvent.devotion_id == devotion.id).order_by(DevotionEvent.created_at)).all()
    return {**brief(devotion), "overview": devotion.overview, "background": devotion.background, "significance": devotion.significance,
            "references": devotion.references, "instructions": devotion.instructions, "steps": devotion.steps,
            "texts": [text_out(t) for t in devotion.texts],
            "events": [{"actor": e.actor, "action": e.action, "from_status": e.from_status, "to_status": e.to_status, "note": e.note, "at": e.created_at} for e in events]}


@router.post("/devotions/{slug}/{action}")
def devotion_action(slug: str, action: str, db: DB, user: Owner):
    devotion = owned_draft(db, slug)
    actor = user.clerk_user_id
    if action == "return":
        before = devotion.status
        svc.reset_approvals(devotion)
        svc.record(db, devotion.id, actor, "returned_for_work", from_status=before, to_status="proposed")
        db.flush()
        return brief(devotion)
    if action not in DEVOTION_FLOW:
        raise HTTPException(404, "Unknown editorial action")
    expected, target = DEVOTION_FLOW[action]
    if devotion.status != expected:
        raise HTTPException(409, f"A devotion can only move to {target} from {expected}; this one is {devotion.status}")
    now = utcnow()
    if action == "verify-source":
        devotion.source_verified_by, devotion.source_verified_at = actor, now
    elif action == "approve":
        devotion.approved_by, devotion.approved_at = actor, now
        devotion.approved_hash = svc.devotion_fingerprint(devotion)
    elif action == "publish":
        unapproved = [t.slot for t in devotion.texts if svc.has_body(t) and t.status != "approved"]
        if unapproved:
            raise HTTPException(409, f"Approve every prayer text first; still pending: {sorted(set(unapproved))}")
        devotion.published_at = now
    devotion.status = target
    svc.record(db, devotion.id, actor, action, from_status=expected, to_status=target)
    db.flush()
    return brief(devotion)


@router.post("/devotions/{slug}/texts/{text_id}/{action}")
def text_action(slug: str, text_id: UUID, action: str, db: DB, user: Owner):
    devotion = owned_draft(db, slug)
    prayer = next((t for t in devotion.texts if t.id == text_id), None)
    if prayer is None:
        raise HTTPException(404, "Prayer text not found")
    if action not in TEXT_FLOW:
        raise HTTPException(404, "Unknown editorial action")
    expected, target = TEXT_FLOW[action]
    if prayer.status != expected:
        raise HTTPException(409, f"A text can only move to {target} from {expected}; this one is {prayer.status}")
    if action == "verify-source" and not (prayer.source_title and prayer.attribution and prayer.license_status not in ("unverified", "restricted")):
        raise HTTPException(422, "Verification needs a cited source, attribution and cleared rights on the text")
    now = utcnow()
    if action == "verify-source":
        prayer.source_verified_by, prayer.source_verified_at = user.clerk_user_id, now
    else:
        prayer.approved_by, prayer.approved_at = user.clerk_user_id, now
        prayer.approved_hash = svc.text_fingerprint(prayer)
    prayer.status = target
    svc.record(db, devotion.id, user.clerk_user_id, f"text_{action.replace('-', '_')}", text_id=prayer.id, from_status=expected, to_status=target)
    db.flush()
    return text_out(prayer)
