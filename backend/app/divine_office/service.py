# ruff: noqa: E501
"""Build the structured Office from the engine's output. Nothing is composed here: texts are the engine's, copied."""

import re
from datetime import date
from functools import lru_cache

from pydantic import BaseModel

from . import units as units_module
from .engine import (
    UPSTREAM_URL,
    VERSION,
    EngineConfig,
    EngineUnavailable,
    run_engine,
    upstream_commit,
)
from .parser import Cell, parse

# The eight canonical hours, in order, with the engine commands (hour names from upstream web/www/horas/horas.dialog).
HOURS = [
    {"slug": "matins", "name": "Matins", "latin": "Matutinum", "command": "prayMatutinum"},
    {"slug": "lauds", "name": "Lauds", "latin": "Laudes", "command": "prayLaudes"},
    {"slug": "prime", "name": "Prime", "latin": "Prima", "command": "prayPrima"},
    {"slug": "terce", "name": "Terce", "latin": "Tertia", "command": "prayTertia"},
    {"slug": "sext", "name": "Sext", "latin": "Sexta", "command": "praySexta"},
    {"slug": "none", "name": "None", "latin": "Nona", "command": "prayNona"},
    {"slug": "vespers", "name": "Vespers", "latin": "Vesperae", "command": "prayVesperae"},
    {"slug": "compline", "name": "Compline", "latin": "Completorium", "command": "prayCompletorium"},
]
IMPLEMENTED = {h["slug"] for h in HOURS if h["command"]}
SEASONS = [("Adv", "Advent"), ("Nat", "Christmastide"), ("Epi", "Time after Epiphany"), ("Quadp", "Septuagesima"),
           ("Quad", "Lent"), ("Pasc", "Eastertide"), ("Pent", "Time after Pentecost")]


class LineOut(BaseModel):
    kind: str
    text: str
    label: str | None = None


class MarkOut(BaseModel):
    """A navigable point inside a section (a nocturn, the Te Deum, a commemoration), found from the engine's own rubric lines."""

    line: int
    kind: str
    latin: str
    english: str | None


class UnitOut(BaseModel):
    """A complete prayer inside this row that may be saved. Lines start..end-1 of the row's cells (both languages)."""

    id: str
    kind: str
    title_latin: str
    title_english: str | None
    start: int
    end: int
    date_specific: bool


class RowOut(BaseModel):
    latin: list[LineOut]
    english: list[LineOut]
    aligned: bool = True      # the engine gave the same number of Latin and English lines for this row
    marks: list[MarkOut] = []
    units: list[UnitOut] = []


class SectionOut(BaseModel):
    id: str
    heading_latin: str | None
    heading_english: str | None
    note_latin: str | None = None
    note_english: str | None = None
    rows: list[RowOut]


class SourceOut(BaseModel):
    name: str
    url: str
    commit: str | None
    version: str
    code_license: str
    texts: str


class OfficeOut(BaseModel):
    date: date
    hour: str
    hour_name: str
    hour_latin: str
    liturgical_day: str | None
    liturgical_day_detail: str | None
    rank: str | None
    season: str | None
    season_code: str | None
    sections: list[SectionOut]
    source: SourceOut


class HourInfo(BaseModel):
    slug: str
    name: str
    latin: str
    available: bool


def hours_listing() -> list[dict]:
    return [{"slug": h["slug"], "name": h["name"], "latin": h["latin"], "available": h["slug"] in IMPLEMENTED} for h in HOURS]


def season_label(code: str, day: date) -> str | None:
    """A reader-friendly season from the engine's own season code (None when the code is not recognised)."""
    for prefix, label in SEASONS:
        if code.startswith(prefix):
            if prefix == "Epi" and day.month >= 10:
                return "Time after Pentecost (Sundays after Epiphany resumed)"   # the engine numbers resumed Sundays as Epiphany Sundays
            return label
    return None


def _lines(cell: Cell) -> list[LineOut]:
    return [LineOut(kind=line.kind, text=line.text, label=line.label) for line in cell.lines]


MARKS = [
    ("nocturn", re.compile(r"^(Nocturnus [IVX]+|Ad Nocturnum)$")),
    ("te_deum", re.compile(r"^Te Deum$")),
    ("commemoration", re.compile(r"^Commemoratio\b")),
]


def _marks(latin: Cell, english: Cell) -> list[MarkOut]:
    aligned = len(latin.lines) == len(english.lines)
    found = []
    for index, line in enumerate(latin.lines):
        if line.kind != "rubric":
            continue
        for kind, pattern in MARKS:
            if pattern.match(line.text):
                found.append(MarkOut(line=index, kind=kind, latin=line.text, english=english.lines[index].text if aligned else None))
                break
    return found


def build_sections(rows: list[tuple[Cell, Cell]], day: date | None = None, hour: str = "") -> list[SectionOut]:
    sections: list[SectionOut] = []
    for latin, english in rows:
        if latin.heading is not None or english.heading is not None or not sections:
            sections.append(SectionOut(
                id=f"s{len(sections) + 1}", heading_latin=latin.heading, heading_english=english.heading,
                note_latin=latin.note, note_english=english.note, rows=[],
            ))
        sections[-1].rows.append(RowOut(
            latin=_lines(latin), english=_lines(english), aligned=len(latin.lines) == len(english.lines), marks=_marks(latin, english),
        ))
    if day is not None:
        _attach_units(sections, rows, day, hour)
    return sections


def _attach_units(sections: list[SectionOut], rows: list[tuple[Cell, Cell]], day: date, hour: str) -> None:
    """Attach the reliably identified saveable units to their rows; withdraw any whose id is not unique in this Office."""
    cursor = 0
    found: list[tuple[SectionOut, RowOut, units_module.Unit]] = []
    for section in sections:
        for row in section.rows:
            latin, english = rows[cursor]
            cursor += 1
            for unit in units_module.row_units(latin, english, section.heading_latin, section.heading_english, day, hour, len(section.rows) == 1):
                found.append((section, row, unit))
    ambiguous = units_module.withdraw_ambiguous([(0, 0, unit) for _, _, unit in found])
    for _section, row, unit in found:
        if unit.id not in ambiguous:
            row.units.append(UnitOut(
                id=unit.id, kind=unit.kind, title_latin=unit.title_latin, title_english=unit.title_english, start=unit.start, end=unit.end,
                date_specific=unit.date_specific,
            ))


def office_source(config: EngineConfig) -> SourceOut:
    return SourceOut(
        name="Divinum Officium", url=UPSTREAM_URL, commit=upstream_commit(config.path) if config.path else None, version=VERSION,
        code_license="MIT (repository LICENSE)",
        texts="Latin and English texts as supplied by Divinum Officium. The repository states one MIT licence for itself and does not "
              "itemize the provenance or redistribution rights of individual translations; those are not verified here.",
    )


@lru_cache(maxsize=64)
def _cached(config: EngineConfig, day: date, hour: str) -> OfficeOut:
    hour_info = next(h for h in HOURS if h["slug"] == hour)
    try:
        parsed = parse(run_engine(config, day, hour_info["command"]))
    except ValueError as exc:
        raise EngineUnavailable(f"The engine's answer could not be read: {exc}") from exc
    sections = build_sections(parsed.rows, day, hour)
    if not sections or not any(row.latin and row.english for section in sections for row in section.rows):
        raise EngineUnavailable("The engine returned no Office text for this date and hour.")
    rank = re.search(r"~\s*(.+)$", parsed.title) if parsed.title else None
    return OfficeOut(
        date=day, hour=hour, hour_name=hour_info["name"], hour_latin=hour_info["latin"],
        liturgical_day=parsed.title or parsed.meta.get("day") or None, liturgical_day_detail=parsed.meta.get("day") or None,
        rank=rank.group(1).strip() if rank else None,
        season=season_label(parsed.meta.get("season_code", ""), day), season_code=parsed.meta.get("season_code") or None,
        sections=sections, source=office_source(config),
    )


def office(config: EngineConfig, day: date, hour: str) -> OfficeOut:
    return _cached(config, day, hour)
