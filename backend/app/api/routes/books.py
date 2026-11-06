from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import Text, cast, func, select, update
from sqlalchemy.exc import IntegrityError

from ...db import utcnow
from ...models import Book, Note
from ...schemas import library as ls
from ...services.library import book_note_counts, book_values
from ..dependencies import DB, CurrentUser, owned_book
from .projects import like_pattern

router = APIRouter(prefix="/api/books")


def duplicate_goodreads(db, user, goodreads_id: str | None, exclude: UUID | None = None):
    if goodreads_id is None:
        return
    statement = select(Book.id).where(Book.user_id == user.id, Book.goodreads_id == goodreads_id)
    if exclude is not None:
        statement = statement.where(Book.id != exclude)
    if db.scalar(statement) is not None:
        raise HTTPException(409, "A book with that Goodreads ID is already in your library")


@router.get("", response_model=list[ls.BookOut])
def list_books(
    db: DB, user: CurrentUser, q: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
):
    statement = select(Book).where(Book.user_id == user.id)
    if q and q.strip():
        pattern = like_pattern(q)
        statement = statement.where(
            func.lower(Book.title).like(pattern, escape="\\")
            | func.lower(cast(Book.authors, Text)).like(pattern, escape="\\")
            | func.lower(func.coalesce(Book.publisher, "")).like(pattern, escape="\\")
            | func.coalesce(Book.isbn_10, "").like(pattern, escape="\\")
            | func.coalesce(Book.isbn_13, "").like(pattern, escape="\\")
        )
    books = list(db.scalars(statement.order_by(func.lower(Book.title), Book.id).limit(limit)))
    counts = book_note_counts(db, [book.id for book in books])
    return [book_values(book, counts) for book in books]


@router.post("", response_model=ls.BookOut, status_code=201)
def create_book(body: ls.BookCreate, db: DB, user: CurrentUser):
    values = body.model_dump()
    values["authors"] = values["authors"] or []
    duplicate_goodreads(db, user, values["goodreads_id"])
    book = Book(**values, user_id=user.id)
    db.add(book)
    try:
        db.flush()
    except IntegrityError as exc:
        raise HTTPException(
            409, "A book with that Goodreads ID is already in your library",
        ) from exc
    return book_values(book, {})


@router.get("/{book_id}", response_model=ls.BookOut)
def read_book(book_id: UUID, db: DB, user: CurrentUser):
    book = owned_book(db, user, book_id)
    return book_values(book, book_note_counts(db, [book.id]))


@router.patch("/{book_id}", response_model=ls.BookOut)
def update_book(book_id: UUID, body: ls.BookPatch, db: DB, user: CurrentUser):
    book = owned_book(db, user, book_id)
    values = body.model_dump(exclude_unset=True)
    if "goodreads_id" in values:
        duplicate_goodreads(db, user, values["goodreads_id"], exclude=book.id)
    for key, value in values.items():
        setattr(book, key, value)
    book.updated_at = utcnow()
    db.flush()
    return book_values(book, book_note_counts(db, [book.id]))


@router.delete("/{book_id}", status_code=204)
def delete_book(book_id: UUID, db: DB, user: CurrentUser, keep_notes: bool = False):
    """Delete a book. Its notes are never deleted: they are kept and unlinked.

    Because that changes the notes, the caller must opt in with ``keep_notes=true`` whenever
    the book has notes. Each kept note remembers the book's title as ``former_book``.
    """
    book = owned_book(db, user, book_id)
    count = book_note_counts(db, [book.id]).get(book.id, 0)
    if count and not keep_notes:
        raise HTTPException(
            409,
            f"{count} note{'s are' if count != 1 else ' is'} linked to this book. "
            "Deleting it keeps the notes but unlinks them; confirm with keep_notes=true.",
        )
    if count:
        db.execute(update(Note).where(Note.book_id == book.id, Note.user_id == user.id).values(
            book_id=None, former_book=book.title[:500],
        ))
    db.delete(book)
    db.flush()
    return Response(status_code=204)
