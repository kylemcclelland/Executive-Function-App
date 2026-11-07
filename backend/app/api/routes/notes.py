from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from ...db import utcnow
from ...models import Note, NoteLink, NoteTag
from ...schemas import library as ls
from ...services.library import (
    SYMMETRIC_LINK_TYPES,
    canonical_ends,
    connection_view,
    normalize_tags,
    suggest_tags,
    tag_catalog,
)
from ..dependencies import (
    DB,
    CurrentUser,
    owned_book,
    owned_library_note,
    owned_note_link,
    owned_project,
)
from .projects import like_pattern

router = APIRouter()


def set_tags(db, user, note: Note, tags: list[str]) -> None:
    """Make the note's tags exactly ``tags``, reusing existing spellings.

    A tag the note already has keeps its spelling; otherwise a tag the user has used on any
    note keeps that spelling; only a genuinely new tag keeps the capitalization as typed.
    """
    mine = {row.tag.casefold(): row.tag for row in note.tag_rows}
    catalog = tag_catalog(db, user.id)
    wanted: dict[str, str] = {}
    for tag in tags:
        key = tag.casefold()
        wanted[key] = mine.get(key) or (catalog[key]["tag"] if key in catalog else tag)
    for row in [row for row in note.tag_rows if row.tag.casefold() not in wanted]:
        note.tag_rows.remove(row)
    present = {row.tag.casefold() for row in note.tag_rows}
    for key, tag in wanted.items():
        if key not in present:
            note.tag_rows.append(NoteTag(tag=tag))


@router.get("/api/notes", response_model=list[ls.NoteBrief])
def list_notes(
    db: DB, user: CurrentUser, q: Annotated[str | None, Query(max_length=200)] = None,
    note_type: ls.NoteType | None = None, book_id: UUID | None = None,
    project_id: UUID | None = None, tag: Annotated[str | None, Query(max_length=60)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
):
    statement = select(Note).where(Note.user_id == user.id)
    if note_type is not None:
        statement = statement.where(Note.note_type == note_type)
    if book_id is not None:
        statement = statement.where(Note.book_id == book_id)
    if project_id is not None:
        statement = statement.where(Note.project_id == project_id)
    if tag:
        wanted = normalize_tags([tag])
        if wanted:
            statement = statement.where(
                select(NoteTag.note_id).where(
                    NoteTag.note_id == Note.id, func.lower(NoteTag.tag) == wanted[0].casefold(),
                ).exists()
            )
    if q and q.strip():
        pattern = like_pattern(q)
        statement = statement.where(
            func.lower(Note.title).like(pattern, escape="\\")
            | func.lower(Note.content).like(pattern, escape="\\")
            | func.lower(func.coalesce(Note.source_location, "")).like(pattern, escape="\\")
            | select(NoteTag.note_id).where(
                NoteTag.note_id == Note.id, func.lower(NoteTag.tag).like(pattern, escape="\\"),
            ).exists()
        )
    return db.scalars(statement.order_by(Note.updated_at.desc(), Note.id).limit(limit)).all()


@router.get("/api/notes/tags", response_model=list[ls.TagSuggestion])
def list_tags(
    db: DB, user: CurrentUser, q: Annotated[str | None, Query(max_length=60)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
):
    """Tags used on any of the user's notes, best matches first, for autocomplete."""
    return suggest_tags(tag_catalog(db, user.id), q, limit)


@router.get("/api/notes/graph", response_model=ls.NoteGraphOut)
def read_graph(db: DB, user: CurrentUser):
    """Every note as a node and every connection as an edge, ready for a future graph view."""
    nodes = db.execute(
        select(Note.id, Note.title, Note.note_type, Note.book_id, Note.project_id)
        .where(Note.user_id == user.id).order_by(Note.created_at, Note.id)
    ).all()
    links = db.scalars(
        select(NoteLink).where(NoteLink.user_id == user.id).order_by(NoteLink.created_at)
    ).all()
    return {
        "nodes": [dict(row._mapping) for row in nodes],
        "edges": [
            {"id": link.id, "source": link.source_note_id, "target": link.target_note_id,
             "link_type": link.link_type, "symmetric": link.link_type in SYMMETRIC_LINK_TYPES,
             "explanation": link.explanation}
            for link in links
        ],
    }


@router.post("/api/notes", response_model=ls.NoteOut, status_code=201)
def create_note(body: ls.NoteCreate, db: DB, user: CurrentUser):
    values = body.model_dump()
    tags = values.pop("tags")
    if values["book_id"] is not None:
        owned_book(db, user, values["book_id"])
    if values["project_id"] is not None:
        owned_project(db, user, values["project_id"])
    note = Note(**values, user_id=user.id)
    set_tags(db, user, note, tags)
    db.add(note)
    db.flush()
    db.refresh(note, ["book", "project"])
    return note


@router.get("/api/notes/{note_id}", response_model=ls.NoteOut)
def read_note(note_id: UUID, db: DB, user: CurrentUser):
    return owned_library_note(db, user, note_id)


@router.patch("/api/notes/{note_id}", response_model=ls.NoteOut)
def update_note(note_id: UUID, body: ls.NotePatch, db: DB, user: CurrentUser):
    note = owned_library_note(db, user, note_id)
    values = body.model_dump(exclude_unset=True)
    tags = values.pop("tags", None)
    if values.get("book_id") is not None:
        owned_book(db, user, values["book_id"])
        note.former_book = None
    if values.get("project_id") is not None:
        owned_project(db, user, values["project_id"])
    for key, value in values.items():
        setattr(note, key, value)
    if tags is not None:
        set_tags(db, user, note, tags)
    note.updated_at = utcnow()
    db.flush()
    db.refresh(note, ["book", "project"])
    return note


@router.delete("/api/notes/{note_id}", status_code=204)
def delete_note(note_id: UUID, db: DB, user: CurrentUser):
    # Connections to and from this note are removed with it (ON DELETE CASCADE).
    db.delete(owned_library_note(db, user, note_id))
    db.flush()
    return Response(status_code=204)


@router.get("/api/notes/{note_id}/connections", response_model=list[ls.ConnectionOut])
def list_connections(note_id: UUID, db: DB, user: CurrentUser):
    note = owned_library_note(db, user, note_id)
    links = db.scalars(
        select(NoteLink).where(
            NoteLink.user_id == user.id,
            (NoteLink.source_note_id == note.id) | (NoteLink.target_note_id == note.id),
        ).order_by(NoteLink.created_at.desc(), NoteLink.id)
    ).all()
    other_ids = {
        link.target_note_id if link.source_note_id == note.id else link.source_note_id
        for link in links
    }
    others = {
        other.id: other for other in db.scalars(select(Note).where(Note.id.in_(other_ids)))
    } if other_ids else {}
    return [
        connection_view(
            link, note.id,
            others[link.target_note_id if link.source_note_id == note.id else link.source_note_id],
        )
        for link in links
    ]


@router.post(
    "/api/notes/{note_id}/connections", response_model=ls.ConnectionOut, status_code=201,
)
def create_connection(note_id: UUID, body: ls.NoteLinkCreate, db: DB, user: CurrentUser):
    note = owned_library_note(db, user, note_id)
    other = owned_library_note(db, user, body.target_note_id)  # ownership of both ends
    if other.id == note.id:
        raise HTTPException(422, "A note cannot be connected to itself")
    source_id, target_id = canonical_ends(note.id, other.id, body.link_type)
    duplicate = db.scalar(select(NoteLink.id).where(
        NoteLink.source_note_id == source_id, NoteLink.target_note_id == target_id,
        NoteLink.link_type == body.link_type,
    ))
    if duplicate is not None:
        raise HTTPException(409, "Those notes are already connected this way")
    link = NoteLink(
        user_id=user.id, source_note_id=source_id, target_note_id=target_id,
        link_type=body.link_type, explanation=body.explanation,
    )
    db.add(link)
    try:
        db.flush()
    except IntegrityError as exc:
        raise HTTPException(409, "Those notes are already connected this way") from exc
    return connection_view(link, note.id, other)


@router.delete("/api/note-links/{link_id}", status_code=204)
def delete_connection(link_id: UUID, db: DB, user: CurrentUser):
    db.delete(owned_note_link(db, user, link_id))
    db.flush()
    return Response(status_code=204)
