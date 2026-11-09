"""Goodreads CSV import: parsing, conservative matching, and safe application.

Only bibliographic facts are read. Reading status, ratings, dates, reviews and shelves are
deliberately ignored. Matching never merges books on similar titles alone, never overwrites a
non-empty field, and never deletes anything.
"""

import csv
import io
import re
import secrets
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from ..db import utcnow
from ..models import Book

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 5000
MAX_AUTHORS = 20
REQUIRED_COLUMNS = ("book id", "title", "author")
PREVIEW_TTL_SECONDS = 15 * 60
PREVIEWS_PER_USER = 3

csv.field_size_limit(5_000_000)  # Goodreads reviews can be long; we never keep them


class GoodreadsFormatError(ValueError):
    """The upload is not a usable Goodreads export. The message is safe to show the user."""


# ------------------------------------------------------------------ ISBNs and text

def unwrap(cell: str) -> str:
    """Strip spreadsheet formula quoting such as ="9781234567890"."""
    value = (cell or "").strip()
    match = re.fullmatch(r'=\s*"(.*)"', value, flags=re.S)
    return (match.group(1) if match else value).strip()


def normalize_isbn(value: str) -> str:
    return re.sub(r"[\s-]", "", value or "").upper()


def valid_isbn13(value: str) -> bool:
    if not re.fullmatch(r"\d{13}", value or ""):
        return False
    total = sum(int(digit) * (1 if index % 2 == 0 else 3) for index, digit in enumerate(value[:12]))
    return (10 - total % 10) % 10 == int(value[12])


def valid_isbn10(value: str) -> bool:
    if not re.fullmatch(r"\d{9}[\dX]", value or ""):
        return False
    digits = [10 if char == "X" else int(char) for char in value]
    return sum((10 - index) * digit for index, digit in enumerate(digits)) % 11 == 0


def isbn10_to_13(value: str) -> str | None:
    """Only used to compare editions; the converted value is never stored."""
    if not valid_isbn10(value):
        return None
    body = "978" + value[:9]
    total = sum(int(digit) * (1 if index % 2 == 0 else 3) for index, digit in enumerate(body))
    return body + str((10 - total % 10) % 10)


def isbn_keys(isbn_10: str | None, isbn_13: str | None) -> set[str]:
    keys = set()
    thirteen = normalize_isbn(isbn_13 or "")
    if valid_isbn13(thirteen):
        keys.add(thirteen)
    converted = isbn10_to_13(normalize_isbn(isbn_10 or ""))
    if converted:
        keys.add(converted)
    return keys


def norm_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", plain.casefold()).split())


def norm_title(value: str) -> str:
    return norm_text(re.sub(r"\s*\([^)]*\)\s*$", "", value or ""))  # drop a trailing "(Series, #1)"


def norm_authors(authors: list[str]) -> tuple[str, ...]:
    return tuple(sorted({name for name in (norm_text(author) for author in authors) if name}))


# ------------------------------------------------------------------ parsing

@dataclass
class Row:
    number: int
    title: str
    authors: list[str]
    goodreads_id: str | None
    isbn_10: str | None
    isbn_13: str | None
    year: int | None
    publisher: str | None
    edition: str | None
    warnings: list[str] = field(default_factory=list)


@dataclass
class Problem:
    row: int
    title: str | None
    kind: str  # invalid | duplicate | ambiguous | warning
    message: str


@dataclass
class ParsedExport:
    rows: list[Row]
    problems: list[Problem]
    total_rows: int


def decode(content: bytes) -> str:
    if not content.strip():
        raise GoodreadsFormatError("The file is empty.")
    if b"\x00" in content[:8192]:
        raise GoodreadsFormatError("That doesn’t look like a CSV text file.")
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise GoodreadsFormatError(
            "The file isn’t UTF-8 text. Use the export straight from Goodreads, "
            "without re-saving it in a spreadsheet."
        ) from exc


def parse_year(*values: str) -> int | None:
    for value in values:
        if re.fullmatch(r"\d{1,4}", value or "") and 1 <= int(value) <= 2200:
            return int(value)
    return None


def parse_export(content: bytes) -> ParsedExport:
    reader = csv.reader(io.StringIO(decode(content), newline=""), strict=True)
    try:
        header = next(reader)
    except (StopIteration, csv.Error) as exc:
        raise GoodreadsFormatError("The file has no header row.") from exc
    columns: dict[str, int] = {}
    for index, name in enumerate(header):
        columns.setdefault(name.strip().casefold(), index)
    missing = [name for name in REQUIRED_COLUMNS if name not in columns]
    if missing:
        raise GoodreadsFormatError(
            "This doesn’t look like a Goodreads library export. It should have the columns "
            "Book Id, Title and Author. In Goodreads, use My Books → Import and export → "
            "Export Library."
        )
    rows: list[Row] = []
    problems: list[Problem] = []
    total = 0
    try:
        for number, record in enumerate(reader, start=2):
            if not any(cell.strip() for cell in record):
                continue
            total += 1
            if total > MAX_ROWS:
                raise GoodreadsFormatError(
                    f"This file has more than {MAX_ROWS} books. Split it into smaller files."
                )

            def cell(name: str, record=record) -> str:
                index = columns.get(name)
                return unwrap(record[index]) if index is not None and index < len(record) else ""

            title = " ".join(cell("title").split())
            if not title:
                problems.append(Problem(number, None, "invalid", "This row has no title."))
                continue
            warnings: list[str] = []
            if len(title) > 300:
                title = title[:300]
                warnings.append("Title was shortened to 300 characters.")
            authors: list[str] = []
            names = [cell("author")] + cell("additional authors").split(",")
            for name in names:
                name = " ".join(name.split())
                if name and name not in authors:
                    authors.append(name)
            if len(authors) > MAX_AUTHORS:
                authors = authors[:MAX_AUTHORS]
                warnings.append(f"Only the first {MAX_AUTHORS} authors were kept.")
            goodreads_id = cell("book id") or None
            if goodreads_id and not re.fullmatch(r"[A-Za-z0-9_-]{1,50}", goodreads_id):
                warnings.append("Ignored an unusable Goodreads ID.")
                goodreads_id = None
            isbn_10 = isbn_13 = None
            for raw in (cell("isbn13"), cell("isbn")):
                candidate = normalize_isbn(raw)
                if not candidate:
                    continue
                if valid_isbn13(candidate):
                    isbn_13 = isbn_13 or candidate
                elif valid_isbn10(candidate):
                    isbn_10 = isbn_10 or candidate
                else:
                    warnings.append(f"Ignored invalid ISBN “{raw}”.")
            rows.append(Row(
                number=number, title=title, authors=authors, goodreads_id=goodreads_id,
                isbn_10=isbn_10, isbn_13=isbn_13,
                year=parse_year(cell("year published"), cell("original publication year")),
                publisher=(" ".join(cell("publisher").split())[:200] or None),
                edition=(" ".join(cell("binding").split())[:200] or None), warnings=warnings,
            ))
    except csv.Error as exc:
        raise GoodreadsFormatError(f"The file isn’t valid CSV ({exc}).") from exc
    if total == 0:
        raise GoodreadsFormatError("No books were found in this file.")
    return ParsedExport(rows=rows, problems=problems, total_rows=total)


# ------------------------------------------------------------------ matching

@dataclass(eq=False)
class Entry:
    """A book known to the planner: an existing book, or one this import would add."""

    book_id: UUID | None
    title: str
    authors: list[str]
    goodreads_id: str | None
    isbn_10: str | None
    isbn_13: str | None
    year: int | None
    publisher: str | None
    edition: str | None
    virtual: bool = False

    @property
    def keys(self) -> set[str]:
        return isbn_keys(self.isbn_10, self.isbn_13)

    @property
    def title_author(self) -> tuple[str, tuple[str, ...]] | None:
        authors = norm_authors(self.authors)
        return (norm_title(self.title), authors) if authors and norm_title(self.title) else None


class Index:
    def __init__(self) -> None:
        self.by_goodreads: dict[str, Entry] = {}
        self.by_isbn: dict[str, list[Entry]] = {}
        self.by_title_author: dict[tuple, list[Entry]] = {}

    def add(self, entry: Entry) -> None:
        if entry.goodreads_id:
            self.by_goodreads.setdefault(entry.goodreads_id, entry)
        for key in entry.keys:
            self.by_isbn.setdefault(key, []).append(entry)
        if entry.title_author:
            self.by_title_author.setdefault(entry.title_author, []).append(entry)

    def remove(self, entry: Entry) -> None:
        if entry.goodreads_id and self.by_goodreads.get(entry.goodreads_id) is entry:
            del self.by_goodreads[entry.goodreads_id]
        for key in entry.keys:
            self.by_isbn[key] = [other for other in self.by_isbn.get(key, []) if other is not entry]
        if entry.title_author:
            self.by_title_author[entry.title_author] = [
                other for other in self.by_title_author.get(entry.title_author, [])
                if other is not entry
            ]


@dataclass
class Planned:
    row: Row
    action: str  # add | match | duplicate | ambiguous
    book_id: UUID | None = None
    reason: str | None = None
    fills: dict = field(default_factory=dict)
    note: str | None = None


FILLABLE = ("authors", "isbn_10", "isbn_13", "year", "publisher", "edition")


def conflicts(row: Row, entry: Entry) -> bool:
    """Differing identifiers mean a different edition; never merge those."""
    if row.goodreads_id and entry.goodreads_id and row.goodreads_id != entry.goodreads_id:
        return True
    row_keys, entry_keys = isbn_keys(row.isbn_10, row.isbn_13), entry.keys
    return bool(row_keys and entry_keys and row_keys.isdisjoint(entry_keys))


def dedupe_key(row: Row):
    if row.goodreads_id:
        return ("goodreads", row.goodreads_id)
    keys = sorted(isbn_keys(row.isbn_10, row.isbn_13))
    if keys:
        return ("isbn", keys[0])
    return ("title_author", norm_title(row.title), norm_authors(row.authors))


def find_match(row: Row, index: Index):
    """Returns ("match", entry, reason) | ("ambiguous", entries) | ("none", note)."""
    if row.goodreads_id and row.goodreads_id in index.by_goodreads:
        return "match", index.by_goodreads[row.goodreads_id], "goodreads_id"
    note = None
    for isbn in (row.isbn_13, row.isbn_10):
        keys = isbn_keys(isbn if isbn and len(isbn) == 10 else None,
                         isbn if isbn and len(isbn) == 13 else None)
        for key in keys:
            candidates = list(dict.fromkeys(index.by_isbn.get(key, [])))
            usable = [entry for entry in candidates if not conflicts(row, entry)]
            if len(usable) == 1:
                return "match", usable[0], "isbn"
            if len(usable) > 1:
                return "ambiguous", usable
            if candidates:
                note = (f"Shares an ISBN with “{candidates[0].title}” but has a different "
                        "Goodreads ID, so it was kept as a separate edition.")
    authors = norm_authors(row.authors)
    if authors and norm_title(row.title):
        found = index.by_title_author.get((norm_title(row.title), authors), [])
        candidates = list(dict.fromkeys(found))
        usable = [entry for entry in candidates if not conflicts(row, entry)]
        if len(usable) == 1:
            return "match", usable[0], "title_author"
        if len(usable) > 1:
            return "ambiguous", usable
    return "none", note


def compute_fills(row: Row, entry: Entry, index: Index) -> dict:
    """Only empty fields are filled; a non-empty value is never replaced."""
    fills: dict = {}
    if not entry.authors and row.authors:
        fills["authors"] = row.authors
    for name, value in (("isbn_10", row.isbn_10), ("isbn_13", row.isbn_13)):
        if value and not getattr(entry, name):
            fills[name] = value
    for name, value in (("year", row.year), ("publisher", row.publisher), ("edition", row.edition)):
        if value and not getattr(entry, name):
            fills[name] = value
    if row.goodreads_id and not entry.goodreads_id and row.goodreads_id not in index.by_goodreads:
        fills["goodreads_id"] = row.goodreads_id
    return fills


def apply_to_entry(entry: Entry, fills: dict, index: Index) -> None:
    if fills:
        index.remove(entry)
        for name, value in fills.items():
            setattr(entry, name, value)
        index.add(entry)


def entry_from_book(book: Book) -> Entry:
    return Entry(
        book_id=book.id, title=book.title, authors=list(book.authors or []),
        goodreads_id=book.goodreads_id, isbn_10=book.isbn_10, isbn_13=book.isbn_13,
        year=book.publication_year, publisher=book.publisher, edition=book.edition,
    )


def plan_import(rows: list[Row], books: list[Book]) -> list[Planned]:
    """Decide, without touching the database, what each row would do. Deterministic."""
    index = Index()
    for book in books:
        index.add(entry_from_book(book))
    seen: set = set()
    plan: list[Planned] = []
    for row in rows:
        key = dedupe_key(row)
        if key in seen:
            plan.append(Planned(row, "duplicate", reason="repeated in this file"))
            continue
        seen.add(key)
        outcome = find_match(row, index)
        if outcome[0] == "ambiguous":
            names = ", ".join(f"“{entry.title}”" for entry in outcome[1][:3])
            plan.append(Planned(row, "ambiguous", reason=f"Could be {names}. Nothing was changed."))
        elif outcome[0] == "match":
            _, entry, reason = outcome
            if entry.virtual:
                plan.append(Planned(row, "duplicate", reason="same book as an earlier row"))
                continue
            fills = compute_fills(row, entry, index)
            apply_to_entry(entry, fills, index)
            plan.append(Planned(row, "match", book_id=entry.book_id, reason=reason, fills=fills))
        else:
            entry = Entry(
                book_id=None, title=row.title, authors=list(row.authors),
                goodreads_id=row.goodreads_id, isbn_10=row.isbn_10, isbn_13=row.isbn_13,
                year=row.year, publisher=row.publisher, edition=row.edition, virtual=True,
            )
            index.add(entry)
            plan.append(Planned(row, "add", note=outcome[1]))
    return plan


def make_book(user_id: UUID, row: Row) -> Book:
    return Book(
        user_id=user_id, title=row.title, authors=list(row.authors), isbn_10=row.isbn_10,
        isbn_13=row.isbn_13, publication_year=row.year, publisher=row.publisher,
        edition=row.edition, goodreads_id=row.goodreads_id,
    )


FIELD_TO_COLUMN = {"year": "publication_year"}


def apply_plan(db, user_id: UUID, plan: list[Planned], books: list[Book]) -> list[dict]:
    """Write the plan. Any failure propagates, so the surrounding transaction rolls back."""
    by_id = {book.id: book for book in books}
    outcomes: list[dict] = []
    for item in plan:
        if item.action == "add":
            book = make_book(user_id, item.row)
            db.add(book)
            outcomes.append({"action": "added", "book": book, "title": book.title})
        elif item.action == "match":
            book = by_id[item.book_id]
            for name, value in item.fills.items():
                setattr(book, FIELD_TO_COLUMN.get(name, name), value)
            if item.fills:
                book.updated_at = utcnow()
            outcomes.append({
                "action": "updated" if item.fills else "matched", "book": book, "title": book.title,
            })
    try:
        db.flush()
    except IntegrityError as exc:
        raise GoodreadsFormatError(
            "Some books conflicted with your existing library, so nothing was imported."
        ) from exc
    return outcomes


# ------------------------------------------------------------------ preview tokens

@dataclass
class PreviewEntry:
    user_id: UUID
    rows: list[Row]
    expires_at: float


class ImportStore:
    """Short-lived, in-memory previews. Nothing about an upload is written to disk."""

    def __init__(self, ttl: float = PREVIEW_TTL_SECONDS, per_user: int = PREVIEWS_PER_USER,
                 clock=time.monotonic) -> None:
        self.ttl, self.per_user, self.clock = ttl, per_user, clock
        self._entries: dict[str, PreviewEntry] = {}
        self._lock = threading.Lock()

    def _purge(self) -> None:
        now = self.clock()
        for token in [t for t, entry in self._entries.items() if entry.expires_at <= now]:
            del self._entries[token]

    def put(self, user_id: UUID, rows: list[Row]) -> str:
        with self._lock:
            self._purge()
            mine = sorted((t for t, e in self._entries.items() if e.user_id == user_id),
                          key=lambda t: self._entries[t].expires_at)
            for token in mine[: max(0, len(mine) - self.per_user + 1)]:
                del self._entries[token]
            token = secrets.token_urlsafe(24)
            self._entries[token] = PreviewEntry(user_id, rows, self.clock() + self.ttl)
            return token

    def get(self, user_id: UUID, token: str) -> PreviewEntry | None:
        with self._lock:
            self._purge()
            entry = self._entries.get(token)
            return entry if entry is not None and entry.user_id == user_id else None

    def discard(self, user_id: UUID, token: str) -> None:
        with self._lock:
            entry = self._entries.get(token)
            if entry is not None and entry.user_id == user_id:
                del self._entries[token]
