import re
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Book, Note, NoteLink, NoteTag

# "Related to" and "Contradicts" are mutual. Supports, Develops and Responds to have a
# direction: "A develops B" says nothing about whether B develops A.
SYMMETRIC_LINK_TYPES = frozenset({"related_to", "contradicts"})
MAX_TAGS = 20
MAX_TAG_LENGTH = 50


def normalize_tags(tags: list[str]) -> list[str]:
    """Trim, collapse spaces and drop a leading #. Capitalization is kept as typed; tags that
    differ only by case or surrounding whitespace are duplicates (the first spelling wins)."""
    seen: dict[str, str] = {}
    for raw in tags:
        tag = re.sub(r"\s+", " ", raw.strip().lstrip("#").strip())[:MAX_TAG_LENGTH].strip()
        if tag:
            seen.setdefault(tag.casefold(), tag)
    return list(seen.values())[:MAX_TAGS]


def tag_catalog(db: Session, user_id: UUID) -> dict[str, dict]:
    """Every tag the user has used, grouped case-insensitively, keyed by its casefolded form.

    The canonical spelling is the most-used variant (ties: alphabetical). Only this user's notes
    are ever consulted.
    """
    rows = db.execute(
        select(NoteTag.tag, func.count()).join(Note, Note.id == NoteTag.note_id)
        .where(Note.user_id == user_id).group_by(NoteTag.tag)
    ).all()
    groups: dict[str, list[tuple[str, int]]] = {}
    for tag, count in rows:
        groups.setdefault(tag.casefold(), []).append((tag, count))
    return {
        key: {"tag": min(variants, key=lambda item: (-item[1], item[0]))[0],
              "count": sum(count for _, count in variants)}
        for key, variants in groups.items()
    }


def suggest_tags(catalog: dict[str, dict], query: str | None, limit: int) -> list[dict]:
    needle = (query or "").strip().lstrip("#").strip().casefold()
    matches = [(key, item) for key, item in catalog.items() if needle in key]
    matches.sort(key=lambda pair: (not pair[0].startswith(needle), -pair[1]["count"], pair[0]))
    return [dict(item) for _, item in matches[:limit]]


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
