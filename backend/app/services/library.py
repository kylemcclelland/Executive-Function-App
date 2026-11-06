import re
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Book, Note, NoteLink

# "Related to" and "Contradicts" are mutual. Supports, Develops and Responds to have a
# direction: "A develops B" says nothing about whether B develops A.
SYMMETRIC_LINK_TYPES = frozenset({"related_to", "contradicts"})
MAX_TAGS = 20
MAX_TAG_LENGTH = 50


def normalize_tags(tags: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for raw in tags:
        tag = re.sub(r"\s+", " ", raw.strip().lstrip("#").strip()).lower()
        if tag:
            seen.setdefault(tag[:MAX_TAG_LENGTH])
    return list(seen)[:MAX_TAGS]


def canonical_ends(note_id: UUID, other_id: UUID, link_type: str) -> tuple[UUID, UUID]:
    """Directional links keep the user's direction; symmetric ones get one stable order."""
    if link_type in SYMMETRIC_LINK_TYPES:
        first, second = sorted((note_id, other_id), key=str)
        return first, second
    return note_id, other_id


def connection_view(link: NoteLink, note_id: UUID, other: Note) -> dict:
    if link.link_type in SYMMETRIC_LINK_TYPES:
        direction = "mutual"
    else:
        direction = "outgoing" if link.source_note_id == note_id else "incoming"
    return {
        "id": link.id, "link_type": link.link_type, "direction": direction,
        "explanation": link.explanation, "created_at": link.created_at, "note": other,
    }


def book_note_counts(db: Session, book_ids: list[UUID]) -> dict[UUID, int]:
    if not book_ids:
        return {}
    return dict(db.execute(
        select(Note.book_id, func.count()).where(Note.book_id.in_(book_ids))
        .group_by(Note.book_id)
    ).all())


def book_values(book: Book, counts: dict[UUID, int]) -> dict:
    return {
        **{column.name: getattr(book, column.name) for column in Book.__table__.columns},
        "note_count": counts.get(book.id, 0),
    }
