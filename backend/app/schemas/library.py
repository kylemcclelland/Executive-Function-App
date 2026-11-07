from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import urlparse
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from . import Input, Output, Title, blank_to_none

NoteType = Literal["general", "reading_note", "quotation", "reflection", "research", "question"]
LinkType = Literal["related_to", "supports", "contradicts", "develops", "responds_to"]
Author = Annotated[str, Field(max_length=200)]
MAX_AUTHORS = 20


def clean_authors(value):
    if value is None:
        return []
    seen: dict[str, None] = {}
    for author in value:
        name = " ".join(str(author).split())
        if name:
            seen.setdefault(name)
    if len(seen) > MAX_AUTHORS:
        raise ValueError(f"At most {MAX_AUTHORS} authors")
    if any(len(name) > 200 for name in seen):
        raise ValueError("Author names are limited to 200 characters")
    return list(seen)


def clean_isbn(value, digits: int):
    value = blank_to_none(value)
    if value is None:
        return None
    compact = str(value).replace("-", "").replace(" ", "").upper()
    body, check = compact[:-1], compact[-1:]
    if len(compact) != digits or not body.isdigit() or not (
        check.isdigit() or (digits == 10 and check == "X")
    ):
        raise ValueError(f"Enter a valid ISBN-{digits}")
    return compact


def clean_cover_url(value):
    value = blank_to_none(value)
    if value is None:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Cover image must be an http or https URL")
    return value


class BookFields(Input):
    authors: list[Author] | None = None
    isbn_10: str | None = None
    isbn_13: str | None = None
    publication_year: int | None = Field(default=None, ge=-3000, le=2200)
    publisher: str | None = Field(default=None, max_length=200)
    edition: str | None = Field(default=None, max_length=200)
    cover_url: str | None = Field(default=None, max_length=2000)
    goodreads_id: str | None = Field(default=None, max_length=50, pattern=r"^[A-Za-z0-9_-]*$")
    description: str | None = Field(default=None, max_length=100000)

    _blank = field_validator(
        "publisher", "edition", "goodreads_id", "description", mode="before",
    )(blank_to_none)

    @field_validator("authors", mode="before")
    @classmethod
    def _authors(cls, value):
        return clean_authors(value) if value is not None else None

    @field_validator("isbn_10", mode="before")
    @classmethod
    def _isbn10(cls, value):
        return clean_isbn(value, 10)

    @field_validator("isbn_13", mode="before")
    @classmethod
    def _isbn13(cls, value):
        return clean_isbn(value, 13)

    @field_validator("cover_url", mode="before")
    @classmethod
    def _cover(cls, value):
        return clean_cover_url(value)


class BookCreate(BookFields):
    title: Title


class BookPatch(BookFields):
    title: Title | None = None

    @model_validator(mode="after")
    def non_null_required(self):
        for field in ("title", "authors"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


BookSort = Literal["title", "title_desc", "recent", "year_desc", "year_asc"]


class BookOut(Output):
    id: UUID
    title: str
    authors: list[str]
    isbn_10: str | None
    isbn_13: str | None
    publication_year: int | None
    publisher: str | None
    edition: str | None
    cover_url: str | None
    goodreads_id: str | None
    description: str | None
    created_at: datetime
    updated_at: datetime
    note_count: int


class BookPage(Output):
    items: list[BookOut]
    total: int
    page: int
    page_size: int
    total_pages: int


def clean_tags(value):
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or not all(isinstance(tag, str) for tag in value):
        raise ValueError("Tags must be a list of text values")
    from ..services.library import normalize_tags

    return normalize_tags(list(value))


class NoteFields(Input):
    note_type: NoteType | None = None
    book_id: UUID | None = None
    project_id: UUID | None = None
    source_location: str | None = Field(default=None, max_length=300)
    tags: list[str] | None = None

    _blank = field_validator("source_location", mode="before")(blank_to_none)

    @field_validator("tags", mode="before")
    @classmethod
    def _tags(cls, value):
        return clean_tags(value)


class NoteCreate(NoteFields):
    title: Title
    content: str = Field(default="", max_length=200000)
    note_type: NoteType = "general"
    tags: list[str] = []


class NotePatch(NoteFields):
    title: Title | None = None
    content: str | None = Field(default=None, max_length=200000)

    @model_validator(mode="after")
    def non_null_required(self):
        for field in ("title", "content", "note_type", "tags"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class TagSuggestion(Output):
    tag: str
    count: int


class NoteBrief(Output):
    id: UUID
    title: str
    note_type: NoteType
    book_id: UUID | None
    book_title: str | None
    project_id: UUID | None
    project_name: str | None
    source_location: str | None
    tags: list[str]
    excerpt: str
    updated_at: datetime


class NoteOut(NoteBrief):
    content: str
    former_book: str | None
    created_at: datetime


class NoteLinkCreate(Input):
    target_note_id: UUID
    link_type: LinkType
    explanation: str | None = Field(default=None, max_length=5000)

    _blank = field_validator("explanation", mode="before")(blank_to_none)


class ConnectionOut(Output):
    id: UUID
    link_type: LinkType
    direction: Literal["outgoing", "incoming", "mutual"]
    explanation: str | None
    created_at: datetime
    note: NoteBrief


class GraphNode(Output):
    id: UUID
    title: str
    note_type: NoteType
    book_id: UUID | None
    project_id: UUID | None


class GraphEdge(Output):
    id: UUID
    source: UUID
    target: UUID
    link_type: LinkType
    symmetric: bool
    explanation: str | None


class NoteGraphOut(Output):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
