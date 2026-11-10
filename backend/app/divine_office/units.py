# ruff: noqa: E501
"""Find the complete prayers inside an Office row, from the engine's own line labels (never from layout alone).

A unit is offered only where every condition holds, otherwise it is simply not offered:
  * the row's Latin and English cells have the same number of lines and the same line kinds across the unit (so the English is the same unit);
  * the boundary is marked by the engine's labels: a psalm heading followed by numbered verses; a canticle heading, an optional scripture
    reference and numbered verses; an antiphon line directly before its psalm or canticle; a hymn introduced by the rubric "Hymnus" and
    followed by plain lines up to the versicle, or a whole "Hymnus" section of plain lines.
Chapters, lessons, responsories and collects are NOT offered: their ends are not marked reliably, and the engine mixes them with versicles,
responses and commemorations. A unit id that would occur twice in one Office is withdrawn (ambiguous boundaries).
"""

import hashlib
import re
from dataclasses import dataclass
from datetime import date

from .parser import Cell, Line

KINDS = ("psalm", "canticle", "hymn", "antiphon")
DATE_SPECIFIC = {"antiphon"}            # an antiphon belongs to its day; psalms, canticles and hymns are fixed texts
ID_PATTERN = re.compile(r"^(psalm|canticle|hymn):[0-9a-f]{16}$|^antiphon:\d{4}-\d{2}-\d{2}:[a-z]+:[0-9a-f]{16}$")


@dataclass
class Unit:
    id: str
    kind: str
    title_latin: str
    title_english: str
    start: int
    end: int                # exclusive
    date_specific: bool


def digest(lines: list[Line]) -> str:
    text = "\n".join(f"{line.kind}|{line.label or ''}|{line.text}" for line in lines)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def unit_id(kind: str, lines: list[Line], day: date, hour: str) -> str:
    h = digest(lines)
    return f"antiphon:{day.isoformat()}:{hour}:{h}" if kind in DATE_SPECIFIC else f"{kind}:{h}"


def _same_shape(latin: list[Line], english: list[Line], start: int, end: int) -> bool:
    return end <= len(english) and [line.kind for line in latin[start:end]] == [line.kind for line in english[start:end]]


def _verses(latin: list[Line], start: int) -> int:
    end = start
    while end < len(latin) and latin[end].kind == "psalm_verse":
        end += 1
    return end


def row_units(latin: Cell, english: Cell, section_latin: str | None, section_english: str | None, day: date, hour: str, single_row: bool) -> list[Unit]:
    """The reliably identified units of one row (positions are line indices within the row's cells)."""
    if len(latin.lines) != len(english.lines):
        return []
    found: list[Unit] = []
    ls, es = latin.lines, english.lines
    for i, line in enumerate(ls):
        if line.kind == "psalm_heading" and re.match(r"^Psalmus\b", line.label or "") and re.match(r"^Psalm\b", es[i].label or ""):
            end = _verses(ls, i + 1)
            if end > i + 1 and _same_shape(ls, es, i, end):
                found.append(Unit(unit_id("psalm", ls[i:end], day, hour), "psalm", line.label, es[i].label, i, end, False))
        elif line.kind == "psalm_heading" and (line.label or "").startswith("Canticum"):
            first = i + 2 if i + 1 < len(ls) and ls[i + 1].kind == "rubric" else i + 1      # the optional scripture reference sits under the heading
            end = _verses(ls, first)
            if end > first and _same_shape(ls, es, i, end):
                named = bool(section_latin and section_latin.startswith("Canticum:") and section_english and ":" in section_english)
                name_l = section_latin.split(":", 1)[1].strip() if named else line.label
                name_e = section_english.split(":", 1)[1].strip() if named else (es[i].label or line.label)
                found.append(Unit(unit_id("canticle", ls[i:end], day, hour), "canticle", name_l, name_e, i, end, False))
        elif line.kind == "antiphon" and i + 1 < len(ls) and ls[i + 1].kind == "psalm_heading" and es[i].kind == "antiphon" and es[i + 1].kind == "psalm_heading":
            following_l = ls[i + 1].label or ""
            following_e = es[i + 1].label or ""
            if following_l and following_e and _same_shape(ls, es, i, i + 2):
                nested = section_latin.split(":", 1)[1].strip() if following_l.startswith("Canticum") and section_latin and section_latin.startswith("Canticum:") else following_l
                nested_e = section_english.split(":", 1)[1].strip() if following_l.startswith("Canticum") and section_english and ":" in section_english else following_e
                found.append(Unit(unit_id("antiphon", ls[i:i + 1], day, hour), "antiphon", f"Antiphona ad {nested}", f"Antiphon to {nested_e}", i, i + 1, True))
        elif line.kind == "rubric" and line.text == "Hymnus" and es[i].kind == "rubric" and es[i].text == "Hymn":
            end = i + 1
            while end < len(ls) and ls[end].kind == "text":
                end += 1
            if end - (i + 1) >= 4 and _same_shape(ls, es, i, end):
                found.append(Unit(unit_id("hymn", ls[i + 1:end], day, hour), "hymn", f"Hymnus: {ls[i + 1].text}", f"Hymn: {es[i + 1].text}", i + 1, end, False))
    if section_latin == "Hymnus" and single_row and ls and all(line.kind == "text" for line in ls) and len(ls) >= 4 and _same_shape(ls, es, 0, len(ls)):
        found.append(Unit(unit_id("hymn", ls, day, hour), "hymn", f"Hymnus: {ls[0].text}", f"Hymn: {es[0].text}", 0, len(ls), False))
    return found


def withdraw_ambiguous(units: list[tuple[int, int, Unit]]) -> set[str]:
    """Ids that occur more than once in one Office: their boundaries cannot be told apart, so none is offered."""
    seen: dict[str, int] = {}
    for _, _, unit in units:
        seen[unit.id] = seen.get(unit.id, 0) + 1
    return {unit_id for unit_id, count in seen.items() if count > 1}
