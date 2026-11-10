#!/usr/bin/env python
# ruff: noqa: E501
"""Slice "The Prayers of the Rosary" (a document the owner supplied) into its prayers, VERBATIM, and write seed_data/rosary_document.json.

    python scripts/import_rosary_prayers.py "<path to The Prayers of the Rosary.txt>"

It never touches a database and writes no wording of its own. Rules, all deterministic:
  * Lines that consist only of a page number (1-6) are page furniture of the PDF export and are dropped. Nothing else is dropped.
  * Each prayer is cut out by its heading line; the English block follows the line "English", the Latin block the line "Latina".
  * The document wraps lines at the page width. Lines inside one block are joined with a single space; a line that begins "V. " or "R. "
    starts a new line, because it is a versicle or response, not a wrapped line. No word, letter or punctuation mark is changed.
  * The document's own introduction to each prayer, its "Full page:" link lines and its "Note:" are kept as source commentary,
    separate from the prayer wording, and are never prayer text.
It stops (exit 1) rather than guess when the document is not shaped as described.
"""

import hashlib
import json
import re
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent / "seed_data" / "rosary_document.json"
PROVENANCE = "User-supplied document: The Prayers of the Rosary"
PAGE_NUMBER = re.compile(r"\d{1,2}")

# heading in the document -> (key, devotion that already holds the same prayer, if any), in the order the document gives them
PRAYERS = [
    ("The Sign of the Cross", "sign-of-the-cross", "sign-of-the-cross"),
    ("The Apostles' Creed", "apostles-creed", "apostles-creed"),
    ("The Our Father", "our-father", "our-father"),
    ("The Hail Mary", "hail-mary", "hail-mary"),
    ("The Glory Be", "glory-be", "glory-be"),
    ("The Fatima Prayer", "fatima-prayer", None),
    ("The Hail Holy Queen", "hail-holy-queen", None),
    ("The Closing Prayer", "closing-prayer", None),
    ("St. Michael the Archangel Prayer", "st-michael-prayer", "prayer-to-st-michael"),
    ("Prayer to St. Joseph", "st-joseph-prayer", None),
]
NOT_A_PRAYER = "Pronouncing the Rosary in Latin"      # a section of advice between two prayers: kept as an observation, not imported


class Stop(SystemExit):
    pass


def fail(message: str):
    raise Stop(f"STOP: {message}")


def clean_lines(text: str) -> tuple[list[str], list[int]]:
    """The document's lines without the standalone page numbers (which are returned separately, with their original line numbers)."""
    lines, pages = [], []
    for number, line in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        if PAGE_NUMBER.fullmatch(line.strip()):
            pages.append(number)
        elif line.strip():
            lines.append((number, line.strip()))
    return lines, pages


def paragraph(lines: list[str]) -> str:
    """Wrapped lines joined with one space; a versicle or response keeps its own line."""
    out: list[str] = []
    for line in lines:
        if not out or line.startswith(("V. ", "R. ")):
            out.append(line)
        else:
            if out[-1].endswith("-"):
                fail(f"A line ends in a hyphen, so joining it would be a guess: {out[-1][-30:]!r}")
            out[-1] += " " + line
    return "\n".join(out)


def parse(raw: bytes) -> dict:
    text = raw.decode("utf-8")
    numbered, pages = clean_lines(text)
    body = [line for _, line in numbered]
    where = {line: n for n, line in numbered}
    headings = [h for h, _, _ in PRAYERS[:8]] + [NOT_A_PRAYER] + [h for h, _, _ in PRAYERS[8:]]
    positions, at = [], {}
    for heading in headings:
        hits = [i for i, line in enumerate(body) if line == heading]
        if not hits or len(hits) > 2 or (len(hits) == 2 and heading != "Prayer to St. Joseph"):    # that one prayer repeats its title above the language markers
            fail(f"Expected the heading {heading!r} once (or its title repeated), found {len(hits)}")
        positions.append(hits[0])
        at[heading] = hits[0]
    if positions != sorted(positions):
        fail("The headings are not in the expected order")
    introduction = body[: positions[0]]
    end_of = {}
    ordered = sorted(positions) + [len(body)]
    for index, start in enumerate(sorted(positions)):
        end_of[start] = ordered[index + 1]
    prayers = []
    for heading, key, related in PRAYERS:
        start = at[heading]
        section = body[start + 1 : end_of[start]]
        # section: Latin title, the document's own introduction, the Latin title again, "EN · LA", "English", ..., "Latina", ...
        try:
            marker = section.index("EN · LA")
            english_at, latin_at = section.index("English"), section.index("Latina")
        except ValueError:
            fail(f"{heading!r} does not have the EN · LA / English / Latina markers")
        latin_title = section[0]
        if section[marker - 1] != section[0] and section[marker - 1] != heading:
            if heading != "St. Michael the Archangel Prayer":          # the document repeats its own short title here
                fail(f"{heading!r}: unexpected line before the language markers")
        if not (marker < english_at < latin_at):
            fail(f"{heading!r}: the markers are out of order")
        about = section[1 : marker - 1]
        english = section[english_at + 1 : latin_at]
        tail = section[latin_at + 1 :]
        latin, extras = [], []
        for line in tail:
            (extras if extras or line.startswith(("Full page:", "Note:")) else latin).append(line)
        if not english or not latin:
            fail(f"{heading!r}: an empty block")
        notes = []
        for line in extras:
            if line.startswith(("Full page:", "Note:")):
                notes.append(line)
            else:
                notes[-1] += " " + line                                   # a wrapped line of a note
        prayers.append({
            "heading_in_file": heading, "key": key, "related_devotion": related, "latin_title": latin_title,
            "introduction": paragraph(about), "english": paragraph(english), "latin": paragraph(latin),
            "commentary_lines": notes,
            "lines_in_file": [where[heading], where[section[-1]]],
        })
    return {
        "provenance": PROVENANCE, "title": "The Prayers of the Rosary", "file_bytes": len(raw), "file_sha256": hashlib.sha256(raw).hexdigest(),
        "document_introduction": paragraph(introduction[1:]), "page_number_lines_dropped": pages,
        "not_imported": {NOT_A_PRAYER: "A section of advice about Latin pronunciation, not a prayer."},
        "prayers": prayers,
    }


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__)
        return 2
    path = Path(argv[0])
    raw = path.read_bytes()
    data = parse(raw)
    data["filename"] = path.name
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for p in data["prayers"]:
        print(f"{p['heading_in_file']}: English {len(p['english'])} chars, Latin {len(p['latin'])} chars, {len(p['commentary_lines'])} commentary line(s)")
    print(f"Wrote {OUT} (document SHA-256 {data['file_sha256']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
