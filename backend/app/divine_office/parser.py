# ruff: noqa: E501
"""Structure the Divinum Officium engine's HTML output without changing a word of it.

The engine returns a table whose rows pair the Latin cell with the English cell. Every cell is cut into lines (at its line breaks) and
each line is labelled from the engine's own markup (red labels such as the versicle and response signs, "Ant.", psalm headings,
psalm verse numbers, rubrics). Text is only ever copied: tags are removed and entities decoded, nothing is added, merged or translated.
"""

import html
import re
from dataclasses import dataclass, field

ROW = re.compile(r"<TR>(.*?)</TR>", re.S | re.I)
CELL = re.compile(r"<TD[^>]*>(.*?)</TD>", re.S | re.I)
NAV = re.compile(r"<DIV ALIGN='right'>.*?</DIV>", re.S | re.I)
HEADING = re.compile(r"""\s*<FONT SIZE='\+1' COLOR="red"><B><I>(.*?)</I></B></FONT>\s*(?:<FONT SIZE='-1' >(.*?)</FONT>)?""", re.S | re.I)
LABEL = re.compile(r"""\s*<FONT COLOR="red"><I>(.*?)</I></FONT>(.*)""", re.S | re.I)
VERSE_NUMBER = re.compile(r"""\s*<FONT SIZE='1' COLOR="red">([^<]*)</FONT>(.*)""", re.S | re.I)
WHOLE_RUBRIC = re.compile(r"""\s*<FONT SIZE='1' COLOR="red">(.*)</FONT>\s*$""", re.S | re.I)
TITLE = re.compile(r"<P ALIGN=CENTER><FONT >(.*?)</FONT></P>", re.S | re.I)
META = re.compile(r"<!--DO-META\t(.*?)-->", re.S)
BREAK = re.compile(r"<br\s*/?>", re.I)
TAG = re.compile(r"<[^>]+>")


def plain(fragment: str) -> str:
    return re.sub(r"[ \t\r\n]+", " ", html.unescape(TAG.sub("", fragment))).replace("\xa0", " ").strip()


@dataclass
class Line:
    kind: str                 # text | versicle | response | antiphon | psalm_heading | psalm_verse | benediction | rubric | labelled
    text: str
    label: str | None = None


@dataclass
class Cell:
    heading: str | None = None
    note: str | None = None
    lines: list[Line] = field(default_factory=list)


def classify(label: str, rest: str) -> Line:
    if label.startswith("℣"):
        return Line("versicle", rest, label)
    if label.startswith("℟"):
        return Line("response", rest, label)
    if label.lower().startswith("ant"):
        return Line("antiphon", rest, label)
    if re.match(r"(Psalmus|Psalm|Canticum|Canticle)\b", label):
        return Line("psalm_heading", rest, label)
    if label.lower().startswith(("benedictio", "benediction")):
        return Line("benediction", rest, label)
    return Line("rubric", label, None) if not rest else Line("labelled", rest, label)


def parse_cell(raw: str) -> Cell:
    cell = Cell()
    body = NAV.sub("", raw, count=1)
    found = HEADING.match(body)
    if found:
        cell.heading, cell.note = plain(found.group(1)), (plain(found.group(2)) if found.group(2) else None)
        body = body[found.end():]
    for piece in BREAK.split(body):
        if not plain(piece):
            continue
        label = LABEL.match(piece)
        number = VERSE_NUMBER.match(piece)
        if label:
            cell.lines.append(classify(plain(label.group(1)), plain(label.group(2))))
        elif number and plain(number.group(2)):
            cell.lines.append(Line("psalm_verse", plain(number.group(2)), plain(number.group(1))))
        elif WHOLE_RUBRIC.match(piece):
            cell.lines.append(Line("rubric", plain(piece)))
        else:
            cell.lines.append(Line("text", plain(piece)))
    return cell


@dataclass
class Parsed:
    title: str | None
    meta: dict
    rows: list[tuple[Cell, Cell]]


def parse_meta(output: str) -> dict:
    """The engine's own computed day data: [season code, day title and rank...] then winner, commemoratio and rank."""
    found = META.search(output)
    if not found:
        return {}
    parts = found.group(1).split("	")
    named = {}
    day = []
    for part in parts[1:]:
        key = part.split("=", 1)[0]
        if key in {"winner", "commemoratio", "rank"} and "=" in part:
            named[key] = part.split("=", 1)[1]
        elif part.strip():
            day.append(part.strip())
    return {"season_code": parts[0].strip(), "day": " ".join(day), **named}


def parse(output: str) -> Parsed:
    title = TITLE.search(output)
    rows = []
    for row in ROW.findall(output):
        cells = CELL.findall(row)
        if len(cells) != 2:
            raise ValueError(f"Expected a Latin and an English cell, found {len(cells)}")
        rows.append((parse_cell(cells[0]), parse_cell(cells[1])))
    return Parsed(plain(title.group(1)) if title else None, parse_meta(output), rows)
