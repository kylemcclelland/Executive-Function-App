"""Optional cover enrichment from the Open Library Covers API (https://openlibrary.org/dev/docs/api/covers).

Designed to be a polite client:

* One request at most every ``REQUEST_INTERVAL_SECONDS`` (4 s), enforced globally across batches.
  Open Library caps ISBN-addressed cover requests at 100 per IP per 5 minutes; 4 s keeps a
  whole run safely under that even before page image loads are counted.
* A 429 (or 503) stops the batch at once, records a cooldown from ``Retry-After`` (seconds or
  HTTP-date), and no network request is made until it passes. The cooldown survives restarts.
* Definite answers (a cover exists / none exists) are cached with their timestamp, so an ISBN is
  not asked about twice. "No cover" is re-checked after ``NOT_FOUND_TTL``. Errors and rate
  limits are never cached.
* No database transaction is held open while waiting on the network: each step reads or writes in
  its own short transaction, so SQLite's write lock is never held across a request.

A cover found this way comes from the ISBN and may show a different edition, so it is only ever
written into an empty cover field and can always be replaced by hand.
"""

import email.utils
import logging
import math
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import exists, func, literal, or_, select
from sqlalchemy.orm import Session

from ..db import utcnow
from ..models import Book, CoverLookup, CoverServiceState

logger = logging.getLogger(__name__)

COVER_URL = "https://covers.openlibrary.org/b/isbn/{isbn}-{size}.jpg"
COVER_ID_URL = "https://covers.openlibrary.org/b/id/{cover_id}-{size}.jpg"
LEGACY_PREFIX = "https://covers.openlibrary.org/b/isbn/"
USER_AGENT = "Studium/1.0 (personal library; local use)"
TIMEOUT_SECONDS = 4.0
REQUEST_INTERVAL_SECONDS = 4.0
DEFAULT_BATCH = 3
MAX_BATCH = 5
MAX_CONSECUTIVE_ERRORS = 2
NOT_FOUND_TTL = timedelta(days=30)
DEFAULT_COOLDOWN_SECONDS = 15 * 60
UNAVAILABLE_COOLDOWN_SECONDS = 60      # a 503 without Retry-After: pause briefly, not 15 min
MIN_COOLDOWN_SECONDS = 10
MAX_COOLDOWN_SECONDS = 24 * 60 * 60
SERVICE = "open_library"
UNAVAILABLE_SERVICE = "open_library_unavailable"
LOOKUP_CHUNK = 400  # keeps IN (...) lists well under SQLite's variable limit

FOUND, NOT_FOUND, RATE_LIMITED, ERROR = "found", "not_found", "rate_limited", "error"
UNAVAILABLE = "unavailable"            # HTTP 503: Open Library itself is having trouble
RATE_LIMIT_REASON, UNAVAILABLE_REASON = "rate_limited", "unavailable"


@dataclass(frozen=True)
class Lookup:
    status: str
    retry_after: float | None = None   # seconds, only meaningful for RATE_LIMITED
    cover_id: int | None = None        # verified numeric cover ID, only meaningful for FOUND
    http_status: int | None = None     # set when the answer came from an HTTP error response


ID_PATH = re.compile(r"/b/id/(\d+)-[SML]\.jpe?g$", re.IGNORECASE)
ID_ARCHIVE_FILE = re.compile(r"^(?:.*/)?(\d+)-[SML]\.jpe?g$", re.IGNORECASE)


def extract_cover_id(final_url: str | None) -> int | None:
    """The numeric cover ID from the URL an ISBN lookup redirected to, when it is unmistakable.

    Open Library serves ``/b/isbn/…`` by redirecting to the cover's canonical file, either
    ``covers.openlibrary.org/b/id/{id}-L.jpg`` or an archive.org zipview URL whose ``file=``
    parameter is ``{id}-L.jpg``. Anything else returns ``None``: an ID is never invented.
    """
    if not final_url:
        return None
    try:
        parts = urllib.parse.urlsplit(final_url)
    except ValueError:
        return None
    match = ID_PATH.search(parts.path)
    if match is None:
        for value in urllib.parse.parse_qs(parts.query).get("file", []):
            match = ID_ARCHIVE_FILE.match(value)
            if match:
                break
    if match is None:
        return None
    cover_id = int(match.group(1))
    return cover_id if cover_id > 0 else None


def parse_retry_after(value: str | None, now: datetime | None = None) -> float | None:
    """Understands both forms of Retry-After: delta-seconds and an HTTP-date."""
    if not value or not value.strip():
        return None
    text = value.strip()
    if text.isdigit():
        return float(int(text))
    try:
        when = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - (now or datetime.now(UTC))).total_seconds())


class Pacer:
    """Spaces requests at least ``interval`` seconds apart, across every batch and caller."""

    def __init__(self, interval: float, clock=time.monotonic, sleep=time.sleep) -> None:
        self.interval, self.clock, self.sleep = interval, clock, sleep
        self._last: float | None = None
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            if self._last is not None:
                remaining = self.interval - (self.clock() - self._last)
                if remaining > 0:
                    self.sleep(remaining)
            self._last = self.clock()

    def finished(self) -> None:
        with self._lock:
            self._last = self.clock()


PACER = Pacer(REQUEST_INTERVAL_SECONDS)


def lookup_cover(isbn: str) -> Lookup:
    """Ask Open Library whether a cover exists for this ISBN. Never raises."""
    request = urllib.request.Request(
        COVER_URL.format(isbn=isbn, size="L") + "?default=false", method="HEAD",
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            if response.status != 200:
                return Lookup(NOT_FOUND)
            return Lookup(FOUND, cover_id=extract_cover_id(response.url))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return Lookup(NOT_FOUND)
        if exc.code == 429:
            header = exc.headers.get("Retry-After") if exc.headers else None
            logger.warning(
                "open_library rate limit: http_status=%s retry_after_header=%r",
                exc.code, header,
            )
            return Lookup(RATE_LIMITED, parse_retry_after(header, utcnow()), http_status=429)
        if exc.code == 503:
            header = exc.headers.get("Retry-After") if exc.headers else None
            logger.warning(
                "open_library unavailable: http_status=%s retry_after_header=%r",
                exc.code, header,
            )
            return Lookup(UNAVAILABLE, parse_retry_after(header, utcnow()), http_status=503)
        logger.warning("open_library http error: http_status=%s", exc.code)
        return Lookup(ERROR, http_status=exc.code)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        logger.warning("open_library network error: %s", type(exc).__name__)
        return Lookup(ERROR)


def cover_url_for(isbn: str, cover_id: int | None = None) -> str:
    """The URL to store on a book: by cover ID when one was verified (those requests are not
    rate limited), otherwise by ISBN, which Open Library counts against a shared IP quota."""
    if cover_id is not None:
        return COVER_ID_URL.format(cover_id=cover_id, size="M")
    return COVER_URL.format(isbn=isbn, size="M")


# ------------------------------------------------------------------ cooldown and cache

def active_cooldown_state(db: Session, now: datetime) -> tuple[datetime | None, str | None]:
    """The latest active pause and why it exists: a rate limit or plain unavailability."""
    best: tuple[datetime | None, str | None] = (None, None)
    for name, reason in ((SERVICE, RATE_LIMIT_REASON), (UNAVAILABLE_SERVICE, UNAVAILABLE_REASON)):
        state = db.get(CoverServiceState, name)
        if state is not None and state.blocked_until is not None and state.blocked_until > now:
            if best[0] is None or state.blocked_until > best[0]:
                best = (state.blocked_until, reason)
    return best


def active_cooldown(db: Session, now: datetime) -> datetime | None:
    return active_cooldown_state(db, now)[0]


def cooldown_info(blocked_until: datetime | None, reason: str | None = None) -> dict:
    if blocked_until is None:
        return {"blocked_until": None, "retry_after_seconds": None, "cooldown_reason": None}
    seconds = max(0, math.ceil((blocked_until - utcnow()).total_seconds()))
    return {
        "blocked_until": blocked_until,
        "retry_after_seconds": seconds,
        "cooldown_reason": reason or RATE_LIMIT_REASON,
    }


def start_cooldown(
    session_factory,
    retry_after: float | None,
    service: str = SERVICE,
    default_seconds: float = DEFAULT_COOLDOWN_SECONDS,
) -> datetime:
    seconds = default_seconds if retry_after is None else retry_after
    seconds = min(max(seconds, MIN_COOLDOWN_SECONDS), MAX_COOLDOWN_SECONDS)
    now = utcnow()
    until = now + timedelta(seconds=seconds)
    with session_factory.begin() as db:
        db.merge(CoverServiceState(name=service, blocked_until=until, updated_at=now))
    return until


def pause_for(session_factory, lookup: Lookup) -> tuple[datetime, str]:
    """Persist the pause a 429 or 503 asks for, and name its reason.

    A rate limit without Retry-After keeps the cautious 15-minute default. Plain
    unavailability without one gets only a short pause: the service may be back any moment,
    and no quota was spent. Either way the batch has already stopped — nothing retries.
    """
    if lookup.status == RATE_LIMITED:
        return start_cooldown(session_factory, lookup.retry_after), RATE_LIMIT_REASON
    return (
        start_cooldown(
            session_factory, lookup.retry_after,
            service=UNAVAILABLE_SERVICE, default_seconds=UNAVAILABLE_COOLDOWN_SECONDS,
        ),
        UNAVAILABLE_REASON,
    )


def record_lookup(session_factory, isbn: str, result: str, cover_id: int | None = None) -> None:
    with session_factory.begin() as db:
        db.merge(CoverLookup(isbn=isbn, result=result, cover_id=cover_id, looked_up_at=utcnow()))


def fresh_not_found(now: datetime):
    """True for a book whose ISBN was recently confirmed to have no cover."""
    return exists().where(
        CoverLookup.isbn == func.coalesce(Book.isbn_13, Book.isbn_10),
        CoverLookup.result == NOT_FOUND, CoverLookup.looked_up_at > now - NOT_FOUND_TTL,
    )


def missing_cover_filter(user_id, skip=(), now: datetime | None = None):
    conditions = [
        Book.user_id == user_id,
        or_(Book.cover_url.is_(None), Book.cover_url == ""),
        or_(Book.isbn_13.is_not(None), Book.isbn_10.is_not(None)),
        ~fresh_not_found(now or utcnow()),
    ]
    if skip:
        conditions.append(Book.id.not_in(list(skip)))
    return conditions


def count_missing(db: Session, user_id, skip=()) -> int:
    return db.scalar(
        select(func.count()).select_from(Book).where(*missing_cover_filter(user_id, skip))
    )


def library_cover_stats(db: Session, user_id) -> dict:
    """Progress numbers for the Library: covers in place, and what the cache already knows."""
    with_covers = db.scalar(
        select(func.count()).select_from(Book).where(
            Book.user_id == user_id, Book.cover_url.is_not(None), Book.cover_url != ""
        )
    )
    lookups = dict(
        db.execute(select(CoverLookup.result, func.count()).group_by(CoverLookup.result)).all()
    )
    return {
        "with_covers": with_covers,
        "found_lookups": lookups.get(FOUND, 0),
        "not_found_lookups": lookups.get(NOT_FOUND, 0),
    }


def legacy_cover_filter(user_id, skip=()):
    """Books whose cover still hotlinks Open Library by ISBN, spending the shared quota on
    every page render. They are upgraded to cover-ID URLs a few at a time."""
    isbn = func.coalesce(Book.isbn_13, Book.isbn_10)
    conditions = [
        Book.user_id == user_id,
        isbn.is_not(None),
        Book.cover_url == literal(LEGACY_PREFIX) + isbn + literal("-M.jpg"),
    ]
    if skip:
        conditions.append(Book.id.not_in(list(skip)))
    return conditions


def replace_cover_url(session_factory, book_id, old_url: str, new_url: str) -> dict | None:
    """Swap one exact URL for another; anything the user changed meanwhile is left alone."""
    with session_factory.begin() as db:
        book = db.get(Book, book_id)
        if book is not None and book.cover_url == old_url and new_url != old_url:
            book.cover_url = new_url
            book.updated_at = utcnow()
            return {"id": book.id, "cover_url": new_url}
    return None


def count_legacy(db: Session, user_id, skip=()) -> int:
    return db.scalar(
        select(func.count()).select_from(Book).where(*legacy_cover_filter(user_id, skip))
    )


def apply_covers(session_factory, pairs: list[tuple]) -> list[dict]:
    """Fill empty cover fields only; a cover that is already set is never replaced."""
    updated: list[dict] = []
    with session_factory.begin() as db:
        for book_id, url in pairs:
            book = db.get(Book, book_id)
            if book is not None and not book.cover_url:
                book.cover_url = url
                book.updated_at = utcnow()
                updated.append({"id": book.id, "cover_url": book.cover_url})
    return updated


def load_cache(session_factory, isbns: list[str]) -> dict[str, CoverLookup]:
    cache: dict[str, CoverLookup] = {}
    with session_factory() as db:
        for start in range(0, len(isbns), LOOKUP_CHUNK):
            chunk = isbns[start:start + LOOKUP_CHUNK]
            for entry in db.scalars(select(CoverLookup).where(CoverLookup.isbn.in_(chunk))):
                db.expunge(entry)
                cache[entry.isbn] = entry
    return cache


# ------------------------------------------------------------------ the batch

def convert_legacy_covers(session_factory, user_id, skip, budget: int, now: datetime) -> dict:
    """Upgrade ISBN-hotlinked cover URLs to verified cover-ID URLs, within ``budget`` requests.

    A URL is only ever replaced when a numeric cover ID was verified from Open Library's own
    redirect; on "no cover", an error, or an ID-less answer the existing URL is kept untouched.
    Ran as the quiet tail of a normal enrichment batch, so it shares its pacing and cooldown.
    """
    out: dict = {"converted": [], "checked": 0, "errors": 0, "checked_ids": [],
                 "blocked_until": None, "cooldown_reason": None}
    with session_factory() as db:
        rows = db.execute(
            select(Book.id, func.coalesce(Book.isbn_13, Book.isbn_10))
            .where(*legacy_cover_filter(user_id, skip)).order_by(Book.title, Book.id)
        ).all()
    if not rows:
        return out
    cache = load_cache(session_factory, list({isbn for _, isbn in rows}))
    requests_made = consecutive_errors = 0
    ids: dict[str, int | None] = {}        # isbn -> verified cover ID (None: leave the URL be)
    for book_id, isbn in rows:
        if isbn in ids:
            cover_id = ids[isbn]
        else:
            entry = cache.get(isbn)
            if entry is not None and entry.result == FOUND and entry.cover_id is not None:
                cover_id = ids[isbn] = entry.cover_id
            elif entry is not None and (
                entry.result == FOUND or entry.looked_up_at > now - NOT_FOUND_TTL
            ):
                cover_id = ids[isbn] = None    # already answered, but without a usable ID
            else:
                if requests_made >= budget:
                    break
                PACER.wait()
                lookup = lookup_cover(isbn)
                PACER.finished()
                requests_made += 1
                out["checked"] += 1
                logger.info(
                    "open_library lookup: op=convert_legacy request=%d result=%s",
                    requests_made, lookup.status,
                )
                if lookup.status in (RATE_LIMITED, UNAVAILABLE):
                    until, reason = pause_for(session_factory, lookup)
                    out["blocked_until"], out["cooldown_reason"] = until, reason
                    logger.warning(
                        "open_library cooldown started: op=convert_legacy request=%d "
                        "reason=%s http_status=%s retry_after=%s blocked_until=%s",
                        requests_made, reason, lookup.http_status, lookup.retry_after,
                        until.isoformat(),
                    )
                    break
                if lookup.status == ERROR:
                    out["errors"] += 1
                    out["checked_ids"].append(book_id)
                    consecutive_errors += 1
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        break
                    continue
                consecutive_errors = 0
                record_lookup(session_factory, isbn, lookup.status, lookup.cover_id)
                cover_id = ids[isbn] = lookup.cover_id if lookup.status == FOUND else None
        if cover_id is not None:
            change = replace_cover_url(
                session_factory, book_id,
                COVER_URL.format(isbn=isbn, size="M"), cover_url_for(isbn, cover_id),
            )
            if change is not None:
                out["converted"].append(change)
        else:
            out["checked_ids"].append(book_id)
    return out


def enrich_covers(session_factory, user_id, limit: int = DEFAULT_BATCH, skip=()) -> dict:
    """One small batch. The caller passes back ``checked_ids`` as ``skip`` to continue.

    ``session_factory`` is used for short, separate transactions; nothing is held open while
    waiting on Open Library.
    """
    limit = max(1, min(limit, MAX_BATCH))
    skip = set(skip)
    now = utcnow()
    stats = {"checked": 0, "found": 0, "not_found": 0, "errors": 0, "cached": 0,
             "rate_limited": False, "unavailable": False, "stopped_early": False}
    with session_factory() as db:
        blocked_until, cooldown_reason = active_cooldown_state(db, now)
        candidates = [
            (row[0], row[1]) for row in db.execute(
                select(Book.id, func.coalesce(Book.isbn_13, Book.isbn_10))
                .where(*missing_cover_filter(user_id, skip, now)).order_by(Book.title, Book.id)
            )
        ]
    updated: list[dict] = []
    converted: list[dict] = []
    checked_ids: list = []
    requests_made = 0
    if blocked_until is not None:   # still cooling down: make no request at all
        stats["rate_limited"] = cooldown_reason == RATE_LIMIT_REASON
        stats["unavailable"] = cooldown_reason == UNAVAILABLE_REASON
        stats["stopped_early"] = True
    else:
        by_isbn: dict[str, list] = {}
        for book_id, isbn in candidates:
            by_isbn.setdefault(isbn, []).append(book_id)
        cache = load_cache(session_factory, list(by_isbn))
        outcomes: dict[str, str] = {}
        urls: dict[str, str] = {}
        applied: set[str] = set()
        consecutive_errors = 0
        for book_id, isbn in candidates:
            outcome = outcomes.get(isbn)
            if outcome is None:
                entry = cache.get(isbn)
                if entry is not None and (
                    entry.result == FOUND or entry.looked_up_at > now - NOT_FOUND_TTL
                ):
                    outcome = outcomes[isbn] = entry.result
                    urls[isbn] = cover_url_for(isbn, entry.cover_id)
                    stats["cached"] += 1
                else:
                    if requests_made >= limit:
                        break
                    PACER.wait()
                    lookup = lookup_cover(isbn)
                    PACER.finished()
                    requests_made += 1
                    stats["checked"] += 1
                    logger.info(
                        "open_library lookup: op=enrich request=%d result=%s",
                        requests_made, lookup.status,
                    )
                    if lookup.status in (RATE_LIMITED, UNAVAILABLE):
                        blocked_until, cooldown_reason = pause_for(session_factory, lookup)
                        logger.warning(
                            "open_library cooldown started: op=enrich request=%d reason=%s "
                            "http_status=%s retry_after=%s blocked_until=%s",
                            requests_made, cooldown_reason, lookup.http_status,
                            lookup.retry_after, blocked_until.isoformat(),
                        )
                        stats["rate_limited"] = cooldown_reason == RATE_LIMIT_REASON
                        stats["unavailable"] = cooldown_reason == UNAVAILABLE_REASON
                        stats["stopped_early"] = True
                        break                      # stop at once; never retry in a loop
                    if lookup.status == ERROR:
                        outcomes[isbn] = ERROR
                        stats["errors"] += 1
                        consecutive_errors += 1
                        if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                            stats["stopped_early"] = True
                            break
                        continue
                    consecutive_errors = 0
                    record_lookup(session_factory, isbn, lookup.status, lookup.cover_id)
                    outcome = outcomes[isbn] = lookup.status
                    urls[isbn] = cover_url_for(isbn, lookup.cover_id)
                    if outcome == FOUND:           # persist progress right away
                        updated += apply_covers(
                            session_factory,
                            [(other, urls[isbn]) for other in by_isbn[isbn]],
                        )
                        applied.add(isbn)
            if outcome == NOT_FOUND:
                stats["not_found"] += 1
                checked_ids.append(book_id)
        leftovers = [
            (other, urls[isbn]) for isbn, outcome in outcomes.items()
            if outcome == FOUND and isbn not in applied for other in by_isbn[isbn]
        ]
        if leftovers:                              # covers already known from the cache
            updated += apply_covers(session_factory, leftovers)
    stats["found"] = len(updated)
    if blocked_until is None and not stats["stopped_early"]:
        legacy = convert_legacy_covers(
            session_factory, user_id, skip | set(checked_ids),
            max(0, limit - requests_made), now,
        )
        converted = legacy["converted"]
        stats["checked"] += legacy["checked"]
        stats["errors"] += legacy["errors"]
        checked_ids += legacy["checked_ids"]
        if legacy["blocked_until"] is not None:
            blocked_until, cooldown_reason = legacy["blocked_until"], legacy["cooldown_reason"]
            stats["rate_limited"] = cooldown_reason == RATE_LIMIT_REASON
            stats["unavailable"] = cooldown_reason == UNAVAILABLE_REASON
            stats["stopped_early"] = True
    stats["converted"] = len(converted)
    with session_factory() as db:
        remaining = count_missing(db, user_id, skip | set(checked_ids))
        legacy_remaining = count_legacy(db, user_id, skip | set(checked_ids))
    return {**stats, "updated": updated + converted, "checked_ids": checked_ids,
            "remaining": remaining, "legacy_remaining": legacy_remaining,
            **cooldown_info(blocked_until, cooldown_reason)}
