from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import select

from ...db import utcnow
from ...models import Book
from ...schemas import imports as schemas
from ...services import covers
from ...services.goodreads import (
    MAX_BYTES,
    GoodreadsFormatError,
    Planned,
    apply_plan,
    parse_export,
    plan_import,
)
from ..dependencies import DB, CurrentUser, current_user_id

router = APIRouter(prefix="/api/books")

PROBLEM_CAP = 50
SAMPLE_SIZE = 10
EXPIRED = "This preview has expired. Choose the file again."
TOO_LARGE = f"That file is too large (the limit is {MAX_BYTES // 2**20} MB)."


async def read_limited_body(request: Request) -> bytes:
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_BYTES:
        raise HTTPException(413, TOO_LARGE)
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BYTES:
            raise HTTPException(413, TOO_LARGE)
        chunks.append(chunk)
    return b"".join(chunks)


def problems_from_plan(plan: list[Planned]) -> list[dict]:
    found = []
    for item in plan:
        if item.action in ("duplicate", "ambiguous"):
            found.append({"row": item.row.number, "title": item.row.title,
                          "kind": item.action, "message": item.reason or ""})
        for message in item.row.warnings + ([item.note] if item.note else []):
            found.append({"row": item.row.number, "title": item.row.title,
                          "kind": "warning", "message": message})
    return found


def user_books(db, user) -> list[Book]:
    return list(db.scalars(select(Book).where(Book.user_id == user.id)))


@router.post("/import/preview", response_model=schemas.ImportPreviewOut)
async def preview_import(request: Request, db: DB, user: CurrentUser):
    """Parse an uploaded Goodreads CSV and report what an import would do. Writes nothing."""
    try:
        parsed = parse_export(await read_limited_body(request))
    except GoodreadsFormatError as exc:
        raise HTTPException(422, str(exc)) from exc
    plan = plan_import(parsed.rows, user_books(db, user))
    store = request.app.state.import_store
    token = store.put(user.id, parsed.rows)
    adds = [item for item in plan if item.action == "add"]
    matches = [item for item in plan if item.action == "match"]
    unidentified = sum(
        1 for item in plan
        if not item.row.goodreads_id and not item.row.isbn_10 and not item.row.isbn_13
    )
    warnings = []
    if unidentified:
        warnings.append(
            f"{unidentified} {'book has' if unidentified == 1 else 'books have'} no Goodreads ID "
            "or ISBN, so they can only be matched by title and author."
        )
    problems = [
        {"row": p.row, "title": p.title, "kind": p.kind, "message": p.message}
        for p in parsed.problems
    ] + problems_from_plan(plan)
    return {
        "token": token, "expires_in_seconds": int(store.ttl),
        "counts": {
            "total_rows": parsed.total_rows, "to_add": len(adds), "matched": len(matches),
            "to_update": sum(1 for item in matches if item.fills),
            "duplicates": sum(1 for item in plan if item.action == "duplicate"),
            "ambiguous": sum(1 for item in plan if item.action == "ambiguous"),
            "invalid": len(parsed.problems),
        },
        "warnings": warnings,
        "problems": sorted(
            problems, key=lambda p: (p["kind"] == "warning", p["row"]),
        )[:PROBLEM_CAP],
        "sample_new": [
            {"title": i.row.title, "authors": i.row.authors, "year": i.row.year,
             "goodreads_id": i.row.goodreads_id}
            for i in adds[:SAMPLE_SIZE]
        ],
        "sample_matched": [
            {"title": i.row.title, "book_id": i.book_id, "reason": i.reason,
             "fills": sorted(i.fills)}
            for i in matches[:SAMPLE_SIZE]
        ],
    }


@router.post("/import/confirm", response_model=schemas.ImportResultOut)
def confirm_import(body: schemas.ImportConfirm, request: Request, db: DB, user: CurrentUser):
    """Apply a previewed import. Only the server-held, validated rows are used."""
    store = request.app.state.import_store
    entry = store.get(user.id, body.token)
    if entry is None:
        raise HTTPException(404, EXPIRED)
    books = user_books(db, user)
    plan = plan_import(entry.rows, books)   # re-planned against the library as it is now
    try:
        outcomes = apply_plan(db, user.id, plan, books)
    except GoodreadsFormatError as exc:
        raise HTTPException(409, str(exc)) from exc
    store.discard(user.id, body.token)
    count = lambda action: sum(1 for item in plan if item.action == action)  # noqa: E731
    added = sum(1 for o in outcomes if o["action"] == "added")
    updated = sum(1 for o in outcomes if o["action"] == "updated")
    matched = sum(1 for o in outcomes if o["action"] in ("matched", "updated"))
    problems = [p for p in problems_from_plan(plan) if p["kind"] != "warning"]
    return {
        "summary": {
            "added": added, "matched": matched, "updated": updated,
            "skipped": count("duplicate") + count("ambiguous"),
            "duplicates": count("duplicate"), "ambiguous": count("ambiguous"), "invalid": 0,
        },
        "problems": problems[:PROBLEM_CAP],
        "books": [
            {"id": o["book"].id, "title": o["title"], "action": o["action"]}
            for o in outcomes if o["action"] != "matched"
        ][:25],
    }


@router.delete("/import/{token}", status_code=204)
def cancel_import(token: str, request: Request, user: CurrentUser):
    """Discard a preview. Nothing was written, so there is nothing to undo."""
    request.app.state.import_store.discard(user.id, token)
    return Response(status_code=204)


@router.get("/covers/missing", response_model=schemas.CoverMissingOut)
def missing_covers(db: DB, user: CurrentUser):
    """How many books could still get a cover, how far enrichment has come, and whether Open
    Library has asked us to wait."""
    blocked = covers.active_cooldown(db, utcnow())
    return {
        "count": covers.count_missing(db, user.id),
        **covers.library_cover_stats(db, user.id),
        **covers.cooldown_info(blocked),
    }


@router.post("/covers/enrich", response_model=schemas.CoverEnrichOut)
def enrich_covers(body: schemas.CoverEnrichRequest, request: Request):
    """Look up covers for one small batch of books that have an ISBN but no cover.

    Requests are paced (one every 2 seconds, globally), answers are cached in the database, and a
    429 stops the batch and starts a cooldown that is honoured until it ends. Existing cover URLs
    are never touched. No database transaction is held while waiting on the network, so this
    endpoint deliberately does not use the per-request session. Call again with ``skip`` set to
    the returned ``checked_ids`` to continue.
    """
    user_id = current_user_id(request)
    skip: list[UUID] = body.skip
    return covers.enrich_covers(request.app.state.session_factory, user_id, body.limit, skip)
