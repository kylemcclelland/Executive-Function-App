from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError

from ...models import Devotion, DevotionBookmark, DevotionEvent, PrayerText
from ...schemas import devotions as ds
from ...services import devotions as svc
from ..dependencies import DB, AnyEditorial, CurrentUser, EditorOnly, get_editorial

# What readers see. Only published devotions, and within them only approved prayer texts.
router = APIRouter()
# Editorial work. Every route needs an explicit role granted in the server's settings; being signed
# in is not enough, and nothing here is reachable by an ordinary account.
editorial_router = APIRouter(
    prefix="/api/editorial/devotions", dependencies=[Depends(get_editorial)],
)


def bookmarked_ids(db, user) -> set[UUID]:
    return set(db.scalars(
        select(DevotionBookmark.devotion_id).where(DevotionBookmark.user_id == user.id)
    ))


@router.get("/api/devotions", response_model=list[ds.DevotionBrief])
def list_devotions(db: DB, user: CurrentUser):
    saved = bookmarked_ids(db, user)
    return [svc.reader_brief(d, d.id in saved, db) for d in svc.published_devotions(db)]


@router.get("/api/devotions/{slug}", response_model=ds.DevotionDetail)
def read_devotion(slug: str, db: DB, user: CurrentUser):
    devotion = svc.published_devotion(db, slug)
    return svc.reader_detail(devotion, devotion.id in bookmarked_ids(db, user), db)


@router.get("/api/editorial-access", response_model=ds.EditorialAccess)
def editorial_access(request: Request, user: CurrentUser):
    """The caller's own editorial roles (both false for an ordinary account). Roles are read from
    the server's settings only; this tells a person what they hold, and grants nothing."""
    settings = request.app.state.settings
    return {
        "is_editor": user_clerk_id(request) in settings.editor_clerk_user_ids,
        "is_approver": user_clerk_id(request) in settings.approver_clerk_user_ids,
    }


def user_clerk_id(request: Request) -> str:
    return request.state.clerk_user_id


@router.put("/api/devotions/{slug}/bookmark", response_model=ds.Bookmark)
def add_bookmark(slug: str, db: DB, user: CurrentUser):
    devotion = svc.published_devotion(db, slug)
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    db.execute(
        insert(DevotionBookmark).values(user_id=user.id, devotion_id=devotion.id)
        .on_conflict_do_nothing()
    )
    return {"bookmarked": True}


@router.delete("/api/devotions/{slug}/bookmark", response_model=ds.Bookmark)
def remove_bookmark(slug: str, db: DB, user: CurrentUser):
    devotion = db.scalar(select(Devotion).where(Devotion.slug == slug))
    if devotion is not None:
        bookmark = db.get(DevotionBookmark, (user.id, devotion.id))
        if bookmark is not None:
            db.delete(bookmark)
            db.flush()
    return {"bookmarked": False}


# ---- Editorial --------------------------------------------------------------------------------
def editorial_devotion(db, devotion_id: UUID) -> Devotion:
    devotion = db.get(Devotion, devotion_id)
    if devotion is None:
        raise HTTPException(404, "Devotion not found")
    return devotion


def editorial_prayer_text(devotion: Devotion, text_id: UUID) -> PrayerText:
    text = next((t for t in devotion.texts if t.id == text_id), None)
    if text is None:
        raise HTTPException(404, "Prayer text not found")
    return text


def flush_or_conflict(db, message: str) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        raise HTTPException(409, message) from exc


def slug_taken(db, slug: str, except_id: UUID | None = None) -> bool:
    found = db.scalar(select(Devotion.id).where(Devotion.slug == slug))
    return found is not None and found != except_id


@editorial_router.get("", response_model=list[ds.EditorialBrief])
def list_for_editors(db: DB, actor: AnyEditorial):
    rows = db.scalars(select(Devotion).order_by(Devotion.title)).all()
    return [svc.editorial_brief(d) for d in rows]


@editorial_router.post("", response_model=ds.EditorialDevotion, status_code=201)
def create_devotion(body: ds.DevotionCreate, db: DB, actor: EditorOnly):
    if slug_taken(db, body.slug):
        raise HTTPException(409, "That address is already used by another devotion")
    devotion = Devotion(**body.model_dump(), created_by=actor.clerk_user_id)
    db.add(devotion)
    flush_or_conflict(db, "That address is already used by another devotion")
    svc.record(db, devotion.id, actor.clerk_user_id, "created", to_status="proposed")
    db.flush()
    return svc.editorial_devotion(devotion, db)


@editorial_router.get("/{devotion_id}", response_model=ds.EditorialDevotion)
def read_for_editors(devotion_id: UUID, db: DB, actor: AnyEditorial):
    return svc.editorial_devotion(editorial_devotion(db, devotion_id), db)


@editorial_router.patch("/{devotion_id}", response_model=ds.EditorialDevotion)
def update_devotion(devotion_id: UUID, body: ds.DevotionPatch, db: DB, actor: EditorOnly):
    devotion = editorial_devotion(db, devotion_id)
    values = body.changes()
    if "slug" in values and slug_taken(db, values["slug"], devotion.id):
        raise HTTPException(409, "That address is already used by another devotion")
    before = devotion.status
    changed = svc.apply_edit(devotion, values, svc.DEVOTION_CONTENT, svc.devotion_fingerprint)
    if changed:
        svc.record(
            db, devotion.id, actor.clerk_user_id, "updated", from_status=before,
            to_status=devotion.status, note=", ".join(changed),
        )
    flush_or_conflict(db, "That address is already used by another devotion")
    return svc.editorial_devotion(devotion, db)


@editorial_router.delete("/{devotion_id}", status_code=204)
def delete_devotion(devotion_id: UUID, db: DB, actor: EditorOnly):
    devotion = editorial_devotion(db, devotion_id)
    if devotion.status in {"approved", "published"}:
        raise HTTPException(409, "Withdraw the approval before deleting a devotion")
    db.delete(devotion)
    db.flush()


@editorial_router.post("/{devotion_id}/transition", response_model=ds.EditorialDevotion)
def transition_devotion(devotion_id: UUID, body: ds.Transition, db: DB, actor: AnyEditorial):
    devotion = editorial_devotion(db, devotion_id)
    svc.transition(db, devotion, body.to, actor, body.note, body.decision)
    db.flush()
    return svc.editorial_devotion(devotion, db)


@editorial_router.get("/{devotion_id}/preview", response_model=ds.EditorialPreview)
def preview_for_editors(devotion_id: UUID, db: DB, actor: AnyEditorial):
    """The devotion as the Oratory would show it, unapproved texts included and marked.

    Editors only; never reachable by a reader."""
    return svc.preview_detail(editorial_devotion(db, devotion_id), db)


@editorial_router.get("/{devotion_id}/events", response_model=list[ds.EventOut])
def list_events(devotion_id: UUID, db: DB, actor: AnyEditorial):
    editorial_devotion(db, devotion_id)
    return db.scalars(
        select(DevotionEvent).where(DevotionEvent.devotion_id == devotion_id)
        .order_by(DevotionEvent.created_at, DevotionEvent.id)
    ).all()


@editorial_router.post(
    "/{devotion_id}/texts", response_model=ds.EditorialText, status_code=201,
)
def create_text(devotion_id: UUID, body: ds.TextCreate, db: DB, actor: EditorOnly):
    devotion = editorial_devotion(db, devotion_id)
    if any(t.slot == body.slot and t.language == body.language for t in devotion.texts):
        raise HTTPException(409, "That prayer text already has a version in this language")
    text = PrayerText(**body.model_dump(), devotion=devotion, entered_by=actor.clerk_user_id)
    db.add(text)
    flush_or_conflict(db, "That prayer text already has a version in this language")
    svc.record(
        db, devotion.id, actor.clerk_user_id, "text_created", text_id=text.id,
        to_status="proposed", note=f"{text.slot}/{text.language}",
    )
    db.flush()
    return svc.editorial_text(text, devotion, svc.events_for(db, devotion.id))


@editorial_router.patch("/{devotion_id}/texts/{text_id}", response_model=ds.EditorialText)
def update_text(devotion_id: UUID, text_id: UUID, body: ds.TextPatch, db: DB, actor: EditorOnly):
    devotion = editorial_devotion(db, devotion_id)
    text = editorial_prayer_text(devotion, text_id)
    values = body.model_dump(exclude_unset=True)
    clash = any(
        other.id != text.id
        and (other.slot, other.language) == (
            values.get("slot", text.slot), values.get("language", text.language),
        )
        for other in devotion.texts
    )
    if clash:
        raise HTTPException(409, "That prayer text already has a version in this language")
    before = text.status
    changed = svc.apply_edit(text, values, svc.TEXT_CONTENT, svc.text_fingerprint)
    if changed:
        # Field names only. Prayer wording is never copied into the log.
        svc.record(
            db, devotion.id, actor.clerk_user_id, "text_updated", text_id=text.id,
            from_status=before, to_status=text.status, note=", ".join(changed),
        )
    flush_or_conflict(db, "That prayer text already has a version in this language")
    return svc.editorial_text(text, devotion, svc.events_for(db, devotion.id))


@editorial_router.delete("/{devotion_id}/texts/{text_id}", status_code=204)
def delete_text(devotion_id: UUID, text_id: UUID, db: DB, actor: EditorOnly):
    devotion = editorial_devotion(db, devotion_id)
    text = editorial_prayer_text(devotion, text_id)
    if text.status == "approved":
        raise HTTPException(409, "Withdraw the approval before deleting an approved text")
    svc.record(
        db, devotion.id, actor.clerk_user_id, "text_deleted", from_status=text.status,
        note=f"{text.slot}/{text.language}",
    )
    devotion.texts.remove(text)
    db.flush()


@editorial_router.post(
    "/{devotion_id}/texts/{text_id}/transition", response_model=ds.EditorialText,
)
def transition_text(
    devotion_id: UUID, text_id: UUID, body: ds.Transition, db: DB, actor: AnyEditorial,
):
    devotion = editorial_devotion(db, devotion_id)
    text = editorial_prayer_text(devotion, text_id)
    svc.transition(db, text, body.to, actor, body.note, body.decision)
    db.flush()
    return svc.editorial_text(text, devotion, svc.events_for(db, devotion.id))
