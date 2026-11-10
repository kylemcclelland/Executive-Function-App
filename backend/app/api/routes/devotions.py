from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ...models import Devotion, DevotionBookmark
from ...schemas import devotions as ds
from ...services import devotions as svc
from ..dependencies import DB, CurrentUser

# The devotion library. Every route needs a signed-in user; a bookmark belongs to its user alone.
router = APIRouter()


def bookmarked_ids(db, user) -> set:
    return set(db.scalars(
        select(DevotionBookmark.devotion_id).where(DevotionBookmark.user_id == user.id)
    ))


@router.get("/api/devotions", response_model=list[ds.DevotionBrief])
def list_devotions(db: DB, user: CurrentUser):
    saved = bookmarked_ids(db, user)
    return [svc.reader_brief(d, d.id in saved, db) for d in svc.library_devotions(db)]


@router.get("/api/devotions/{slug}", response_model=ds.DevotionDetail)
def read_devotion(slug: str, db: DB, user: CurrentUser):
    devotion = svc.library_devotion(db, slug)
    return svc.reader_detail(devotion, devotion.id in bookmarked_ids(db, user), db)


@router.put("/api/devotions/{slug}/bookmark", response_model=ds.Bookmark)
def add_bookmark(slug: str, db: DB, user: CurrentUser):
    devotion = svc.library_devotion(db, slug)
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
