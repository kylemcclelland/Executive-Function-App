from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from . import Input, Output


class ImportCounts(Output):
    total_rows: int
    to_add: int
    matched: int
    to_update: int
    duplicates: int
    ambiguous: int
    invalid: int


class ImportProblem(Output):
    row: int
    title: str | None
    kind: Literal["invalid", "duplicate", "ambiguous", "warning"]
    message: str


class SampleNew(Output):
    title: str
    authors: list[str]
    year: int | None
    goodreads_id: str | None


class SampleMatch(Output):
    title: str
    book_id: UUID
    reason: Literal["goodreads_id", "isbn", "title_author"]
    fills: list[str]


class ImportPreviewOut(Output):
    token: str
    expires_in_seconds: int
    counts: ImportCounts
    warnings: list[str]
    problems: list[ImportProblem]
    sample_new: list[SampleNew]
    sample_matched: list[SampleMatch]


class ImportConfirm(Input):
    token: str = Field(min_length=8, max_length=200)


class ImportedBook(Output):
    id: UUID
    title: str
    action: Literal["added", "updated", "matched"]


class ImportSummary(Output):
    added: int
    matched: int
    updated: int
    skipped: int
    duplicates: int
    ambiguous: int
    invalid: int


class ImportResultOut(Output):
    summary: ImportSummary
    problems: list[ImportProblem]
    books: list[ImportedBook]


class CoverEnrichRequest(Input):
    limit: int = Field(default=3, ge=1, le=5)
    skip: list[UUID] = Field(default=[], max_length=5000)


class CoverUpdate(Output):
    id: UUID
    cover_url: str


class CoverEnrichOut(Output):
    checked: int
    found: int
    not_found: int
    errors: int
    cached: int
    converted: int
    rate_limited: bool
    stopped_early: bool
    blocked_until: datetime | None
    retry_after_seconds: int | None
    updated: list[CoverUpdate]
    checked_ids: list[UUID]
    remaining: int
    legacy_remaining: int


class CoverMissingOut(Output):
    count: int
    with_covers: int
    found_lookups: int
    not_found_lookups: int
    blocked_until: datetime | None = None
    retry_after_seconds: int | None = None
