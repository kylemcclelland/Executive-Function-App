#!/usr/bin/env python
# ruff: noqa: E501
"""Authorized editorial normalization of the user-supplied Latin transcription, and nothing else.

    python backend/scripts/seed_data/latin_normalization.py        # rewrites docs/latin-normalization-diff.md

The ORIGINAL verbatim transcription stays exactly as imported (seed_data/user_supplied_latin.json, with the file's hash). This module
applies ONLY the corrections the owner authorized, deterministically, and records every change:

  1. holy name: the whole word "Iesus" becomes "Jesus" (no other form and no substring is touched);
  2. the invisible soft hyphen U+00AD is removed;
  3. a missing space after a comma is added in two named places in the Apostles' Creed;
  4. a comma after "gratia plena" in the Ave Maria, because the selected edition prints one (see EDITION);
  5. trailing spaces and tabs at the end of lines are removed, and CRLF line endings become LF.

Each rule must apply EXACTLY the expected number of times, or the run stops: it cannot quietly do more or less than authorized. Any
other proposed change (a different word form, capitalisation, further punctuation, spelling convention) is NOT applied: it is listed in
PROPOSALS with its justification and source, for the owner's review. Nothing here translates, paraphrases or modernizes.
"""

import difflib
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ID = "latin-normalization-v1"
OUT = HERE.parents[2] / "docs" / "latin-normalization-diff.md"
SHY = "­"
EDITION = ("Compendium of the Catechism of the Catholic Church (Libreria Editrice Vaticana, 2005), Appendix A: Common Prayers, the Latin Ave Maria "
           "(consulted for punctuation only; nothing is reproduced). It prints a comma after “plena”. The 1889 Missale Romanum (Pustet) prints a colon there, "
           "which is liturgical punctuation, not a comma.")

# slug -> rule -> exactly how many times it must apply
EXPECTED = {
    "our-father": {"trailing_whitespace": 1},
    "hail-mary": {"soft_hyphen": 1, "gratia_plena_comma": 1, "trailing_whitespace": 3},
    "apostles-creed": {"comma_space": 2},
    "glory-be": {},
    "the-angelus": {"holy_name": 3},
    "regina-caeli": {},
}
COMMA_SPACES = [("caelos,sedet", "caelos, sedet"), ("communionem,remissionem", "communionem, remissionem")]
GRATIA = ("Ave Maria, gratia plena\r\n\r\nDominus tecum", "Ave Maria, gratia plena,\r\n\r\nDominus tecum")

# Proposed, NOT applied: each changes a word, a grammatical form, capitalisation or punctuation beyond what was authorized.
PROPOSALS = [
    ("apostles-creed", "“Et in Iesum Christum”", "“Et in Jesum Christum”",
     "Consistency with the authorized Iesus → Jesus. This is a different grammatical form (the accusative), so it was not changed automatically.",
     "Owner's standardization; the Vatican Compendium (2005) prints “Iesum”."),
    ("regina-caeli", "“Domini nostri Iesu Christi”", "“Domini nostri Jesu Christi”",
     "Consistency with the authorized Iesus → Jesus. This is the genitive “Iesu”, a different form, so it was not changed automatically.",
     "Owner's standardization; the Vatican Compendium (2005) prints “Iesu”."),
    ("hail-mary", "“Sancta Maria mater Dei,”", "“Sancta Maria, Mater Dei,”",
     "A comma after the vocative “Maria” and a capital M in “Mater”. This changes capitalisation and punctuation, so it needs your decision.",
     "Compendium 2005, Appendix A prints “Sancta Maria, Mater Dei”; so does the Angelus in the same file you supplied."),
    ("hail-mary", "“Ave Maria,”", "“Ave, Maria,”",
     "A comma after “Ave”. Optional: many traditional editions omit it.",
     "Compendium 2005, Appendix A prints “Ave, Maria”; the 1889 Missale Romanum prints “Ave Maria”."),
    ("hail-mary", "one phrase per paragraph, no end punctuation (“Dominus tecum”, “benedicta tu in mulieribus,”)",
     "full sentences with capitals, as in the Angelus copy (“Dominus tecum. Benedicta tu in mulieribus, …”)",
     "The two copies of the Hail Mary in your file are laid out differently. Decide whether they should match.", "Your own Angelus text in the same file."),
    ("pater-noster", "“Amen” with no full stop (our-father), against “Amen.” elsewhere in the file",
     "“Amen.”", "A trivial inconsistency, left as supplied.", "Your own file."),
    ("all", "consonantal “i” (eius, iudicare, Iesum, Iesu) beside the authorized “Jesus”",
     "“ejus”, “judicare”, “Jesum”, “Jesu”, or revert to “Iesus”",
     "After Iesus → Jesus the Latin mixes the “J” and “I” conventions. Older ecclesiastical printings use “j” throughout; the Vatican Compendium (2005) uses “i” throughout, including “Iesus”. Decide which convention you want.",
     "Compendium 2005 (all “i”); older printings such as the 1889 Missale Romanum (“Jesse”)."),
]
# Reviewed and left alone: legitimate traditional variants, not errors.
VARIANTS = [
    "Pater noster: “panem nostrum quotidianum” is the traditional liturgical form (Luke 11:3), not the Vulgate Matthew “supersubstantialem”.",
    "Glory Be: sparse commas (“Gloria Patri et Filio et Spiritui Sancto”) and a semicolon are both found; punctuation varies by edition.",
    "Creed: “caelos/caeli/caelis” use the “ae” spelling consistently (older printings use “coelos”); “descendit ad inferos” and “carnis resurrectionem” are the standard wording.",
    "Angelus and Regina Caeli: the versicles, responses and collects read as the traditional texts; “Genetricem” and “Genitrix” are both correct in their places.",
]


def _count(rule: str, n: int, slug: str, found: dict) -> None:
    found[rule] = found.get(rule, 0) + n


def normalize(slug: str, original: str) -> tuple[str, dict]:
    text, found = original, {}
    n = len(re.findall(r"\bIesus\b", text))
    text = re.sub(r"\bIesus\b", "Jesus", text)
    _count("holy_name", n, slug, found)
    n = text.count(SHY)
    text = text.replace(SHY, "")
    _count("soft_hyphen", n, slug, found)
    for before, after in COMMA_SPACES:
        n = text.count(before)
        text = text.replace(before, after)
        _count("comma_space", n, slug, found)
    if slug == "hail-mary":
        n = text.count(GRATIA[0])
        text = text.replace(GRATIA[0], GRATIA[1])
        _count("gratia_plena_comma", n, slug, found)
    lines = text.split("\r\n")
    cleaned = [line.rstrip(" \t") for line in lines]
    n = sum(1 for a, b in zip(lines, cleaned, strict=True) if a != b)
    _count("trailing_whitespace", n, slug, found)
    result = "\n".join(cleaned)
    found = {rule: count for rule, count in found.items() if count}
    if found != EXPECTED[slug]:
        raise SystemExit(f"{slug}: the corrections applied {found}, but exactly {EXPECTED[slug]} were authorized. Stopping.")
    return result, found


def apply_all(data: dict) -> dict:
    """slug -> original, normalized, hashes and counts, for every text in user_supplied_latin.json."""
    out = {}
    for item in data["texts"]:
        original = item["body"]
        if hashlib.sha256(original.encode("utf-8")).hexdigest() != item["body_sha256"]:
            raise SystemExit(f"{item['devotion_slug']}: the original transcription no longer matches its recorded hash.")
        normalized, counts = normalize(item["devotion_slug"], original)
        out[item["devotion_slug"]] = {
            "original": original, "normalized": normalized, "counts": counts,
            "original_sha256": item["body_sha256"], "normalized_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        }
    return out


def describe(counts: dict) -> str:
    parts = {
        "holy_name": "“Iesus” → “Jesus”", "soft_hyphen": "soft hyphen U+00AD removed", "comma_space": "space added after a comma",
        "gratia_plena_comma": "comma added after “gratia plena”", "trailing_whitespace": "trailing whitespace removed",
    }
    return "; ".join(f"{parts[rule]} ({n})" for rule, n in counts.items()) + ("; " if counts else "") + "CRLF line endings → LF"


def show(line: str) -> str:
    return line.replace(SHY, "‹U+00AD›").replace("\t", "‹TAB›").rstrip("\r") + ("‹trailing space›" if line.rstrip("\r").endswith(" ") else "")


def render(data: dict, changes: dict) -> str:
    lines = [
        "# Latin prayer normalization: before and after", "",
        f"Editorial normalization `{ID}` of the user-supplied transcription (`{data['filename']}`, {data['file_bytes']} bytes, SHA-256 `{data['file_sha256']}`).",
        "The original file in Downloads is unchanged, and the original verbatim transcription is preserved in `backend/scripts/seed_data/user_supplied_latin.json`.",
        "Only the corrections you authorized were applied. **Nothing was verified, approved or published**, and a corrected text still needs its own review. "
        "Hidden characters and trailing spaces are shown as ‹…› markers below.", "",
        "## Applied (authorized)", "", "| Prayer | Corrections | Original SHA-256 | Normalized SHA-256 |", "|---|---|---|---|",
    ]
    for slug, c in changes.items():
        lines.append(f"| {slug} | {describe(c['counts'])} | `{c['original_sha256'][:16]}…` | `{c['normalized_sha256'][:16]}…` |")
    lines += ["", f"Punctuation evidence for the comma after “gratia plena”: {EDITION}", ""]
    for slug, c in changes.items():
        before, after = c["original"].split("\r\n"), c["normalized"].split("\n")
        diff = [line for line in difflib.unified_diff([show(x) for x in before], [show(x) for x in after], "original (verbatim)", "normalized", n=0, lineterm="") if not line.startswith(("---", "+++", "@@"))]
        lines += [f"### {slug}", ""]
        if not diff:
            lines += ["No line changed apart from CRLF → LF.", ""]
        else:
            lines += ["```diff"] + diff + ["```", ""]
    lines += ["## Proposed, NOT applied (for your review)", "", "| Prayer | Now | Proposed | Why | Source |", "|---|---|---|---|---|"]
    lines += [f"| {slug} | {now} | {proposed} | {why} | {source} |" for slug, now, proposed, why, source in PROPOSALS]
    lines += ["", "## Reviewed and left alone (legitimate traditional variants)", ""] + [f"- {v}" for v in VARIANTS] + [""]
    return "\n".join(lines)


def main() -> None:
    data = json.loads((HERE / "user_supplied_latin.json").read_text(encoding="utf-8"))
    OUT.write_text(render(data, apply_all(data)), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    sys.exit(main())
