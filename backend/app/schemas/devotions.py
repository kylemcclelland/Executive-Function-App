from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import urlparse
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from . import Input, Output, Title, blank_to_none

DevotionStatus = Literal["proposed", "source_verified", "pending_approval", "approved", "published"]
LicenseStatus = Literal[
    "unverified", "restricted", "public_domain", "licensed", "permission_granted",
]
Decision = Literal["return_for_research", "reject_text", "reject_approval", "withdraw"]
StepKind = Literal["instruction", "prayer", "response"]

# "preview" is the front end's layout-preview route; a devotion may never take its address.
RESERVED_SLUGS = {"preview"}
Slug = Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]
SlotKey = Annotated[
    str, Field(min_length=1, max_length=60, pattern=r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$"),
]
Language = Annotated[str, Field(max_length=12, pattern=r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$")]
Note = Annotated[str | None, Field(default=None, max_length=2000)]


def web_url(value):
    """Only http(s) links are stored, so a citation can never carry a script or data URL."""
    value = blank_to_none(value)
    if value is None:
        return None
    parsed = urlparse(value)
    if len(value) > 2000 or parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Enter a web address starting with http:// or https://")
    return value


def reject_null(value):
    if value is None:
        raise ValueError("This field cannot be cleared")
    return value


def blanks_are_unset(*fields: str):
    return field_validator(*fields, mode="before")(lambda cls, value: blank_to_none(value))


def never_cleared(*fields: str):
    return field_validator(*fields, mode="before")(lambda cls, value: reject_null(value))


def must_be_web_url(*fields: str):
    return field_validator(*fields, mode="before")(lambda cls, value: web_url(value))


class SourceReference(Input):
    label: Title
    url: str | None = None

    check_url = must_be_web_url("url")


class Step(Input):
    """One place in a devotion's sequence. Holds structure and instruction, never prayer wording."""

    kind: StepKind
    title: Annotated[str | None, Field(max_length=200)] = None
    instruction: Annotated[str | None, Field(max_length=2000)] = None
    text_slot: SlotKey | None = None
    # A prayer used here that is kept in another devotion (reused, never copied). Its wording is
    # shown only if that devotion is itself published and the text approved.
    devotion_slug: Slug | None = None
    repeat: Annotated[int | None, Field(ge=1, le=150)] = None
    section: Annotated[str | None, Field(max_length=120)] = None
    # Steps of one group are alternatives the reader chooses between (a set of mysteries); steps
    # with no group are always part of the sequence.
    group: Annotated[str | None, Field(max_length=80)] = None
    # A traditional custom rather than a core element: shown as optional, and its prayer need not
    # be approved for the devotion to be published.
    optional: bool = False

    blank_is_unset = blanks_are_unset("title", "instruction", "section", "group")

    @model_validator(mode="after")
    def coherent(self):
        if self.kind == "instruction":
            if not self.instruction:
                raise ValueError("An instruction step needs instruction text")
            if self.text_slot is not None or self.devotion_slug is not None:
                raise ValueError("An instruction step cannot point at a prayer text")
        elif self.text_slot is None:
            raise ValueError("A prayer or response step must name the prayer text it uses")
        return self


class StepOut(Output):
    kind: StepKind
    title: str | None
    instruction: str | None
    text_slot: str | None
    devotion_slug: str | None = None
    repeat: int | None
    section: str | None
    group: str | None = None
    optional: bool = False


class SourceReferenceOut(Output):
    label: str
    url: str | None


Instruction = Annotated[str, Field(min_length=1, max_length=2000)]


class DevotionCreate(Input):
    slug: Slug
    title: Title
    subtitle: Annotated[str | None, Field(max_length=300)] = None
    category: Annotated[str | None, Field(max_length=100)] = None
    estimated_minutes: Annotated[int | None, Field(gt=0, le=1440)] = None
    overview: Annotated[str, Field(min_length=1, max_length=20000)]
    background: Annotated[str | None, Field(max_length=50000)] = None
    significance: Annotated[str | None, Field(max_length=50000)] = None
    references: Annotated[list[SourceReference], Field(max_length=50)] = []
    instructions: Annotated[list[Instruction], Field(max_length=100)] = []
    steps: Annotated[list[Step], Field(max_length=1000)] = []
    choice_label: Annotated[str | None, Field(max_length=60)] = None

    blank_is_unset = blanks_are_unset(
        "subtitle", "category", "background", "significance", "choice_label",
    )

    @field_validator("slug")
    @classmethod
    def not_reserved(cls, value):
        if value in RESERVED_SLUGS:
            raise ValueError("That address is reserved")
        return value

    @field_validator("overview", mode="after")
    @classmethod
    def overview_present(cls, value):
        if not value.strip():
            raise ValueError("The overview cannot be blank")
        return value.strip()

    @field_validator("instructions", mode="after")
    @classmethod
    def instructions_trimmed(cls, value):
        cleaned = [item.strip() for item in value]
        if not all(cleaned):
            raise ValueError("Instructions cannot be blank")
        return cleaned


class DevotionPatch(Input):
    slug: Slug | None = None
    title: Title | None = None
    subtitle: Annotated[str | None, Field(max_length=300)] = None
    category: Annotated[str | None, Field(max_length=100)] = None
    estimated_minutes: Annotated[int | None, Field(gt=0, le=1440)] = None
    overview: Annotated[str | None, Field(min_length=1, max_length=20000)] = None
    background: Annotated[str | None, Field(max_length=50000)] = None
    significance: Annotated[str | None, Field(max_length=50000)] = None
    references: Annotated[list[SourceReference] | None, Field(max_length=50)] = None
    instructions: Annotated[list[Instruction] | None, Field(max_length=100)] = None
    steps: Annotated[list[Step] | None, Field(max_length=1000)] = None
    choice_label: Annotated[str | None, Field(max_length=60)] = None

    blank_is_unset = blanks_are_unset(
        "subtitle", "category", "background", "significance", "choice_label",
    )
    not_null = never_cleared("slug", "title", "overview", "references", "instructions", "steps")

    def changes(self) -> dict:
        """Only the fields the client sent, with nested items dumped in full (no missing keys)."""
        sent = self.model_dump(exclude_unset=True, exclude={"references", "steps"})
        for name in ("references", "steps"):
            if name in self.model_fields_set:
                sent[name] = [item.model_dump() for item in getattr(self, name)]
        return sent

    @field_validator("slug")
    @classmethod
    def not_reserved(cls, value):
        if value in RESERVED_SLUGS:
            raise ValueError("That address is reserved")
        return value

    @field_validator("overview", mode="after")
    @classmethod
    def overview_present(cls, value):
        if not value.strip():
            raise ValueError("The overview cannot be blank")
        return value.strip()

    @field_validator("instructions", mode="after")
    @classmethod
    def instructions_trimmed(cls, value):
        cleaned = [item.strip() for item in value]
        if not all(cleaned):
            raise ValueError("Instructions cannot be blank")
        return cleaned


def exact_body(value: str) -> str:
    """Prayer wording is kept exactly as entered: never trimmed, re-wrapped or normalised.

    Empty means "no wording held" (rights not cleared, or not yet obtained). Whitespace alone is not
    wording and is refused.
    """
    if value and not value.strip():
        raise ValueError("The prayer text cannot be only spaces")
    if "\x00" in value:
        raise ValueError("The prayer text contains an invalid character")
    return value


class TextFields(Input):
    """The cited facts about a prayer text. Optional here; required before it can be verified."""

    title: Annotated[str | None, Field(max_length=300)] = None
    is_translation: bool = False
    translator: Annotated[str | None, Field(max_length=300)] = None
    source_title: Annotated[str | None, Field(max_length=500)] = None
    source_authority: Annotated[str | None, Field(max_length=500)] = None
    source_edition: Annotated[str | None, Field(max_length=300)] = None
    source_date: Annotated[str | None, Field(max_length=100)] = None
    source_url: str | None = None
    source_retrieved_at: datetime | None = None
    attribution: Annotated[str | None, Field(max_length=1000)] = None
    license_status: LicenseStatus = "unverified"
    license_notes: Annotated[str | None, Field(max_length=5000)] = None
    position: Annotated[int, Field(ge=0, le=10000)] = 0

    blank_is_unset = blanks_are_unset(
        "title", "translator", "source_title", "source_authority", "source_edition",
        "source_date", "attribution", "license_notes",
    )
    check_url = must_be_web_url("source_url")


class TextCreate(TextFields):
    slot: SlotKey
    language: Language
    body: Annotated[str, Field(max_length=50000)] = ""

    keep_exact = field_validator("body")(lambda cls, value: exact_body(value))


class TextPatch(Input):
    slot: SlotKey | None = None
    language: Language | None = None
    body: Annotated[str | None, Field(max_length=50000)] = None
    title: Annotated[str | None, Field(max_length=300)] = None
    is_translation: bool | None = None
    translator: Annotated[str | None, Field(max_length=300)] = None
    source_title: Annotated[str | None, Field(max_length=500)] = None
    source_authority: Annotated[str | None, Field(max_length=500)] = None
    source_edition: Annotated[str | None, Field(max_length=300)] = None
    source_date: Annotated[str | None, Field(max_length=100)] = None
    source_url: str | None = None
    source_retrieved_at: datetime | None = None
    attribution: Annotated[str | None, Field(max_length=1000)] = None
    license_status: LicenseStatus | None = None
    license_notes: Annotated[str | None, Field(max_length=5000)] = None
    position: Annotated[int | None, Field(ge=0, le=10000)] = None

    blank_is_unset = blanks_are_unset(
        "title", "translator", "source_title", "source_authority", "source_edition",
        "source_date", "attribution", "license_notes",
    )
    check_url = must_be_web_url("source_url")
    not_null = never_cleared(
        "slot", "language", "body", "is_translation", "license_status", "position",
    )
    keep_exact = field_validator("body")(lambda cls, value: exact_body(value))


class Transition(Input):
    to: DevotionStatus
    note: Note
    # Names what the editor or approver is doing when they send something back or turn it down.
    # A decision needs a reason, recorded in the editorial log.
    decision: Decision | None = None

    @model_validator(mode="after")
    def reasoned(self):
        if self.decision and not (self.note and self.note.strip()):
            raise ValueError("Give a reason for this decision")
        return self


# ---- What a reader sees: only ever approved, published content --------------------------------
class TextSourceOut(Output):
    title: str | None
    authority: str | None = None
    edition: str | None
    date: str | None = None
    translator: str | None
    is_translation: bool
    attribution: str | None
    url: str | None
    license_status: LicenseStatus


class ReaderText(Output):
    id: UUID
    slot: str
    language: str
    title: str | None
    body: str
    # The devotion that holds this text: a step may reuse a prayer kept in another devotion.
    devotion_slug: str
    source: TextSourceOut


class DevotionBrief(Output):
    id: UUID
    slug: str
    title: str
    subtitle: str | None
    category: str | None
    estimated_minutes: int | None
    bookmarked: bool
    has_text: bool


class DevotionDetail(DevotionBrief):
    overview: str
    background: str | None
    significance: str | None
    references: list[SourceReferenceOut]
    instructions: list[str]
    steps: list[StepOut]
    choice_label: str | None = None
    texts: list[ReaderText]


class Bookmark(Output):
    bookmarked: bool


# ---- What an editor sees: everything, with its status ----------------------------------------
class EventOut(Output):
    id: UUID
    text_id: UUID | None
    actor: str
    action: str
    from_status: str | None
    to_status: str | None
    note: str | None
    created_at: datetime


class EditorialText(Output):
    id: UUID
    devotion_slug: str
    slot: str
    language: str
    position: int
    title: str | None
    body: str
    # False when no wording is held (for instance because its rights are not cleared).
    has_body: bool
    is_translation: bool
    translator: str | None
    source_title: str | None
    source_authority: str | None
    source_edition: str | None
    source_date: str | None
    source_url: str | None
    source_retrieved_at: datetime | None
    attribution: str | None
    license_status: LicenseStatus
    license_notes: str | None
    # True only for public-domain, licensed or permitted wording.
    rights_cleared: bool
    status: Literal["proposed", "source_verified", "pending_approval", "approved"]
    entered_by: str
    source_verified_by: str | None
    source_verified_at: datetime | None
    approved_by: str | None
    approved_at: datetime | None
    # False once the wording or its citation changed after approval: readers no longer see it.
    approval_current: bool
    # What still stands between this text and its next step.
    problems: list[str]
    # The most recent decision or move on this text (why it was sent back, rejected, approved...).
    last_event: EventOut | None = None
    updated_at: datetime


class TextSummary(Output):
    slot: str
    language: str
    status: Literal["proposed", "source_verified", "pending_approval", "approved"]
    license_status: LicenseStatus
    has_body: bool
    source_verified: bool


class EditorialBrief(Output):
    id: UUID
    slug: str
    title: str
    category: str | None
    status: DevotionStatus
    prose_origin: str | None
    texts: list[TextSummary]
    texts_approved: int
    texts_total: int
    updated_at: datetime


class EditorialDevotion(Output):
    id: UUID
    slug: str
    title: str
    subtitle: str | None
    category: str | None
    estimated_minutes: int | None
    overview: str
    background: str | None
    significance: str | None
    references: list[SourceReferenceOut]
    instructions: list[str]
    steps: list[StepOut]
    choice_label: str | None = None
    prose_origin: str | None = None
    status: DevotionStatus
    created_by: str
    source_verified_by: str | None
    source_verified_at: datetime | None
    approved_by: str | None
    approved_at: datetime | None
    published_at: datetime | None
    approval_current: bool
    problems: list[str]
    # What still prevents publishing, in plain words (empty when it could be published).
    publication_problems: list[str]
    texts: list[EditorialText]
    updated_at: datetime


class PreviewText(ReaderText):
    status: Literal["proposed", "source_verified", "pending_approval", "approved"]
    approval_current: bool
    # Whether a reader would see this text right now.
    publicly_visible: bool
    has_body: bool
    rights_cleared: bool
    license_notes: str | None = None


class EditorialPreview(DevotionDetail):
    """The devotion as the Oratory would show it, including what is not approved. Editors only."""

    texts: list[PreviewText]
    devotion_status: DevotionStatus
    prose_origin: str | None = None


class EditorialAccess(Output):
    is_editor: bool
    is_approver: bool
