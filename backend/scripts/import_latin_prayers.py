#!/usr/bin/env python
# ruff: noqa: E501
"""Import a user-supplied file of Latin prayers, verbatim, into seed_data/user_supplied_latin.json.

    python backend/scripts/import_latin_prayers.py "C:/Users/me/Downloads/latin_prayers_file.txt"

Nothing is typed, translated, corrected or normalised here. The file is read as bytes and decoded as UTF-8, split into prayers
only at the heading lines it contains, and each prayer's wording is the text between its heading and the next one, with only the
blank lines around it and the final line ending removed. Everything inside is kept exactly: spelling, capitalisation, punctuation,
spaces (including trailing ones), line endings (CRLF as in the file), and any invisible characters. Each body is then checked
against the original file, and the run stops if anything differs.

Provenance recorded for each text: "User-supplied Latin text", the original filename, the SHA-256 of the whole file, the heading it
appeared under and its line numbers. The file names no author, edition, publisher or rights, so none is recorded and the rights
status is "unverified". Characters and spacing that look unusual are LISTED as observations; they are never changed.
"""

import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

OUT = Path(__file__).resolve().parent / "seed_data" / "user_supplied_latin.json"
# The heading lines the file uses, mapped to the devotion each belongs to. Any other heading is not imported.
HEADINGS = {
    "Pater Noster (Our Father)": "our-father", "Ave Maria (Hail Mary)": "hail-mary", "Apostle's Creed": "apostles-creed",
    "Glory Be": "glory-be", "Angelus": "the-angelus", "Regina Caeli": "regina-caeli",
}
PROVENANCE = "User-supplied Latin text"
CRLF = "\r\n"


def parse(raw: bytes) -> tuple[str, list[dict]]:
    text = raw.decode("utf-8")
    if text.count("\r") != text.count(CRLF) or text.count("\n") != text.count(CRLF):
        raise SystemExit("The file mixes line endings; refusing to guess how to import it.")
    lines = text.split(CRLF)
    marks = [(n, line.strip()) for n, line in enumerate(lines) if line.strip() in HEADINGS]
    if [h for _, h in marks] != list(HEADINGS):
        raise SystemExit(f"Headings are missing or out of the expected order: {[h for _, h in marks]}")
    prayers = []
    for index, (heading_at, heading) in enumerate(marks):
        end = marks[index + 1][0] if index + 1 < len(marks) else len(lines)
        content = [n for n in range(heading_at + 1, end) if lines[n].strip()]   # the lines that hold anything
        first, last = content[0], content[-1]
        # Only the blank lines around the prayer and the final line ending are dropped; the rest is exact.
        body = CRLF.join(lines[first:last + 1])
        prayers.append({"heading": heading, "devotion_slug": HEADINGS[heading], "first_line": first + 1, "last_line": last + 1, "body": body})
    return text, prayers


def observations(body: str) -> list[str]:
    found = []
    for char in sorted({c for c in body if ord(c) > 127}):
        found.append(f"contains the character U+{ord(char):04X} ({unicodedata.name(char, 'unnamed')}), kept as supplied")
    glued = sorted({m.group(0) for m in re.finditer(r"[A-Za-z]+[,;:][A-Za-z]+", body)})
    if glued:
        found.append("no space after punctuation in " + ", ".join(f"“{g}”" for g in glued) + " (kept as supplied)")
    if any(line != line.rstrip(" ") for line in body.split(CRLF)):
        found.append("has trailing spaces at the end of some lines (kept as supplied)")
    return found


def main(argv=None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1:
        print(__doc__)
        return 2
    path = Path(arguments[0])
    raw = path.read_bytes()
    file_hash = hashlib.sha256(raw).hexdigest()
    text, prayers = parse(raw)
    entries = []
    for prayer in prayers:
        body = prayer["body"]
        if text.count(body) != 1:
            raise SystemExit(f"{prayer['heading']}: the wording does not match the file exactly (found {text.count(body)} times)")
        entries.append({
            "devotion_slug": prayer["devotion_slug"], "slot": "main", "language": "la", "body": body,
            "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(), "heading_in_file": prayer["heading"],
            "lines_in_file": f"{prayer['first_line']}-{prayer['last_line']}", "observations": observations(body),
        })
    OUT.write_text(json.dumps({"version": 1, "provenance": PROVENANCE, "filename": path.name, "file_sha256": file_hash, "file_bytes": len(raw), "texts": entries}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{path.name}: {len(raw)} bytes, SHA-256 {file_hash}")
    for e in entries:
        print(f"  {e['heading_in_file']:<28} -> {e['devotion_slug']:<16} lines {e['lines_in_file']:<8} {len(e['body'])} chars  " + ("; ".join(e["observations"]) or "no observations"))
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
