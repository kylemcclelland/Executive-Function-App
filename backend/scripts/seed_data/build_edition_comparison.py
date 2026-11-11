#!/usr/bin/env python
# ruff: noqa: E501
"""Generate docs/rosary-edition-comparison.md: the Rosary document's wording against every edition already held.

    python backend/scripts/seed_data/build_edition_comparison.py

Read-only: it compares seed_data/rosary_document.json with prayer_sources.json and the normalized user-supplied Latin, changes none of
them, and decides nothing. The assessments (what kind of difference, which edition to prefer) are the author's, written below
next to the evidence, and are recommendations for the owner to accept or reject.
"""

import difflib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import latin_normalization as norm  # noqa: E402

OUT = HERE.parents[2] / "docs" / "rosary-edition-comparison.md"
DOC = json.loads((HERE / "rosary_document.json").read_text(encoding="utf-8"))
SOURCES = {(t["devotion_slug"], t["slot"], t["language"]): t for t in json.loads((HERE / "prayer_sources.json").read_text(encoding="utf-8"))["texts"] if t["body"]}
LATIN = json.loads((HERE / "user_supplied_latin.json").read_text(encoding="utf-8"))
NORMALIZED = {slug: result["normalized"] for slug, result in norm.apply_all(LATIN).items()}
ORIGINAL = {t["devotion_slug"]: t["body"] for t in LATIN["texts"]}

# prayer key in the document -> where the existing text is held: (devotion, slot)
HELD = {
    "sign-of-the-cross": ("sign-of-the-cross", "main"), "apostles-creed": ("apostles-creed", "main"), "our-father": ("our-father", "main"),
    "hail-mary": ("hail-mary", "main"), "glory-be": ("glory-be", "main"), "hail-holy-queen": ("the-holy-rosary", "hail-holy-queen"),
    "closing-prayer": ("the-holy-rosary", "rosary-concluding-prayer"), "st-michael-prayer": ("prayer-to-st-michael", "main"),
}
NAMES = {
    "sign-of-the-cross": "The Sign of the Cross", "apostles-creed": "The Apostles' Creed", "our-father": "The Our Father", "hail-mary": "The Hail Mary",
    "glory-be": "The Glory Be", "fatima-prayer": "The Fatima Prayer", "hail-holy-queen": "The Hail Holy Queen", "closing-prayer": "The Closing Prayer",
    "st-michael-prayer": "St. Michael the Archangel Prayer", "st-joseph-prayer": "Prayer to St. Joseph",
}
LANGUAGE = {"en": "English", "la": "Latin"}
SPELLING = {  # word pairs that are spelling conventions, not different words (existing, document)
    ("Jesus", "Iesus"), ("Jesum", "Iesum"), ("exules", "exsules"), ("lacrymarum", "lacrimarum"), ("exilium", "exsilium"), ("misericordiæ", "misericordiae"), ("Hevæ.", "Hevae."),
    ("amongst", "among"), ("towards", "toward"),
}

# What kind of difference each pair is, and what is recommended. Evidence is in the table above each entry; none of this is applied.
ASSESSMENT = {
    ("sign-of-the-cross", "en"): ("Legitimate traditional variant (\"Holy Ghost\" / \"Holy Spirit\"). Not an error.", "Document wording is the form in current common use; the held edition is the 1885 form. Prefer the **document** wording only once its source is identified; until then the **held edition** is the only one whose rights are verified."),
    ("sign-of-the-cross", "la"): ("No difference.", "No conflict. Keep the held Latin (verified public-domain source) which the document confirms word for word."),
    ("apostles-creed", "en"): ("Mostly legitimate traditional variants (\"Ghost\"/\"Spirit\", \"arose\"/\"rose\", \"sitteth\"/\"is seated\"). The document's own text is inconsistent: \"He descended … He rose … from thence he will come\" (lower-case \"he\" for the same subject, mid-prayer), an apparent transcription or editing slip in the document. The document also reads \"Holy Spirit, the holy Catholic Church\" (the held edition capitalizes \"Holy Catholic Church\" and \"Communion of Saints\"). Unresolved: which phrasing is wanted.", "Keep the **held edition** for publication until the document's source is known: its provenance is verified and it is internally consistent. If you prefer the modern wording, adopt the document's wording after correcting the lower-case \"he\" against a named source (not changed here)."),
    ("apostles-creed", "la"): ("Punctuation only (comma → semicolon between the clauses). Same words. The held text is the owner-supplied Latin, normalized as authorized.", "Equal on rights (both unverified). **Unresolved**: both punctuations are plausible. Keep the held text until a named source settles it."),
    ("our-father", "en"): ("Punctuation only (colon → semicolon, comma → semicolon). Same words.", "Keep the **held edition** (verified source); the difference is only punctuation, so either reads the same."),
    ("our-father", "la"): ("Punctuation and capitalization only: the held Latin has semicolons and capitalized clause openings (\"Sanctificetur\", \"Adveniat\", \"Fiat\", \"Et\"); the document uses full stops and lower case. Same words. Also a line-structure difference (the held text is laid out in separate lines).", "Both unverified. Recommend the **document**, whose punctuation reads as ordinary sentences and matches its own English; the held text is the owner's own file, so this is the owner's call. Unresolved."),
    ("hail-mary", "en"): ("Legitimate traditional variants (\"amongst\"/\"among\") and punctuation (\"grace!\" → \"grace,\", \"thee:\" → \"thee;\"). Same prayer.", "Keep the **held edition** until the document's source is known; document wording is the more modern and may be preferred by readers."),
    ("hail-mary", "la"): ("One orthographic convention difference: \"Jesus\" (held; the owner authorized Iesus → Jesus for the supplied Latin) against \"Iesus\" (document). The rest is punctuation: the document has \"tecum. Benedicta\" and \"Maria, Mater\"; the held text has a paragraph break after \"plena,\" and no comma after \"Maria\".", "**Unresolved**, a decision for you: the I/J convention. The document uses \"Iesus\" throughout, in conflict with your earlier normalization to \"Jesus\". Recommend the held text until you decide the convention."),
    ("glory-be", "en"): ("Legitimate traditional variant (\"Holy Ghost\" / \"Holy Spirit\"). Not an error.", "As for the Sign of the Cross."),
    ("glory-be", "la"): ("Punctuation and capitalization only (\"Sancto; sicut\" → \"Sancto. Sicut\", \"nunc,\" → \"nunc\"). Same words.", "Both unverified; either is acceptable. **Unresolved**, low stakes."),
    ("hail-holy-queen", "en"): ("A different English rendering: legitimate traditional variants (\"sons\"/\"children\", \"mournings and weepings\"/\"mourning and weeping\", \"pious\"/\"loving\", \"towards\"/\"toward\") and a different structure: the document adds the versicle and response (\"V. Pray for us … R. That we may be made worthy …\"), which the held edition (Gahan, 1844) does not have; the held edition has \"our exile ended\" where the document has none (the document's \"after this our exile show unto us\" is the more usual form).", "**Unresolved.** Keep the held edition as the verified baseline. The versicle and response belong to the Rosary's closing and the document is the only text here that has them; adopting them means adopting the document's wording as a whole, so decide together with the source question."),
    ("hail-holy-queen", "la"): ("Orthographic variants (\"Hevæ\"/\"Hevae\", \"exules\"/\"exsules\", \"lacrymarum\"/\"lacrimarum\", \"exilium\"/\"exsilium\", \"Jesum\"/\"Iesum\", ligatures) and punctuation; the document adds the versicle and response (\"V. Ora pro nobis, sancta Dei Genitrix. R. Ut digni efficiamur promissionibus Christi.\"). Same prayer.", "Legitimate variants, no apparent error. **Unresolved**: the held text (Lings, 1899, verified public-domain source) uses older spelling; the document has the versicle and response. Decide with the English."),
    ("closing-prayer", "en"): ("A different English rendering of the same collect: legitimate traditional variants and capitalization (\"his life, death, resurrection\" / \"His Life, Death, and Resurrection\"; \"most blessed Virgin Mary\" / \"Blessed Virgin Mary\"; \"upon those mysteries\" / \"on these mysteries of the most holy Rosary\"; \"while\" added). The document's \"most holy Rosary\" follows the Latin \"sacratissimo … Rosario\" more closely.", "**Unresolved.** Keep the held edition (verified source) until the document's is identified; the document's is a more literal reading of the Latin."),
    ("st-michael-prayer", "en"): ("Different English renderings of the same Latin (\"malice\"/\"wickedness\", \"Command him, O God\"/\"May God rebuke him\", \"beseech Thee\"/\"pray\", \"roam through\"/\"prowl about\", \"the other evil spirits\"/\"all evil spirits\"). A genuine translation variant, not an error.", "**Unresolved.** The document's is the form most Catholics use today; the held edition (Hammer, 1909) is a verified older translation. Translation rights of the document's wording are unknown."),
}


def tokens(value: str) -> list[str]:
    return re.findall(r"\S+", value)


def letters(word: str) -> str:
    return re.sub(r"[^\w]", "", word, flags=re.UNICODE)


def classify(old: str, new: str) -> str:
    if not old:
        return "added in the document"
    if not new:
        return "only in the held edition"
    a, b = tokens(old), tokens(new)
    if len(a) == len(b) and all(letters(x) == letters(y) for x, y in zip(a, b)):
        return "punctuation only"
    if len(a) == len(b) and all(letters(x).casefold() == letters(y).casefold() for x, y in zip(a, b)):
        return "capitalization / punctuation only"
    if len(a) == len(b) and all(letters(x) == letters(y) or (x.strip(".,;:!"), y.strip(".,;:!")) in SPELLING for x, y in zip(a, b)):
        return "spelling convention"
    return "different words"


def differences(old: str, new: str) -> list[tuple[str, str, str]]:
    a, b = tokens(old), tokens(new)
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag != "equal":
            before, after = " ".join(a[i1:i2]), " ".join(b[j1:j2])
            out.append((before, after, classify(before, after)))
    return out


def held_text(key: str, language: str):
    """(wording, source description) of the edition already held for this prayer, or None."""
    where = HELD.get(key)
    if where is None:
        return None
    devotion, slot = where
    if language == "la" and devotion in NORMALIZED and slot == "main":
        return NORMALIZED[devotion], f"Owner-supplied Latin (`latin_prayers_file.txt`), as normalized under `{norm.ID}`; rights unverified; held on `{devotion}`"
    record = SOURCES.get((devotion, slot, language))
    if record is None:
        return None
    return record["body"], f"{record['source_title']}, {record['source_authority']}; {record['source_edition']}; {record['license_status'].replace('_', ' ')}; held on `{devotion}`, slot `{slot}`"


def cell(value: str) -> str:
    return "`" + (value.replace("`", "'").replace("|", "\\|") or "(nothing)") + "`"


def build() -> str:
    lines = [
        "# Rosary edition comparison", "",
        "*Generated by `backend/scripts/seed_data/build_edition_comparison.py`. Read-only: it compares the newly imported Rosary document with the editions already held and **changes nothing**. "
        "Both editions are preserved; no wording was reconciled, replaced, approved or published. The assessments are recommendations for the owner to accept or reject.*", "",
        f"* **New document:** *{DOC['title']}*, `{DOC['filename']}`, SHA-256 `{DOC['file_sha256']}` (rights unverified; see the rights review below). Stored on The Holy Rosary in slots `collection-<prayer>`.",
        "* **Held editions compared:** `prayer_sources.json` (English, and Latin for the Sign of the Cross and Hail Holy Queen), and the owner-supplied Latin as **normalized** (`user_supplied_latin.json` after `latin_normalization.py`), which is the wording stored in the database.",
        "* Differences are word-level (whitespace and line wrapping are ignored in the table; line structure is noted separately). \"Punctuation only\" means the same letters; "
        "\"spelling convention\" means the same word spelled by a different convention (for example Jesus / Iesus).", "",
    ]
    summary = []
    for prayer in DOC["prayers"]:
        for language, field in (("en", "english"), ("la", "latin")):
            held = held_text(prayer["key"], language)
            summary.append((prayer, language, held))
    comparable = [s for s in summary if s[2]]
    identical = [s for s in comparable if s[2][0] == s[0]["english" if s[1] == "en" else "latin"]]
    lines += ["## Summary", "",
              f"* The document has 10 prayers (20 texts). **{len(comparable)} texts have an existing edition to compare** with: {sum(1 for s in comparable if s[1] == 'en')} English and {sum(1 for s in comparable if s[1] == 'la')} Latin.",
              f"* **{len(identical)} are identical** ({', '.join(f'{NAMES[s[0]['key']]} ({LANGUAGE[s[1]]})' for s in identical)}); **{len(comparable) - len(identical)} differ**.",
              f"* **{len(summary) - len(comparable)} texts have no existing edition**, so there is nothing to conflict with: {', '.join(f'{NAMES[s[0]['key']]} ({LANGUAGE[s[1]]})' for s in summary if not s[2])}.",
              "* **Correction.** My previous report said the document differed from \"17 of 18 comparable texts\". That figure was wrong: it was computed with a slot mapping that left the Hail Holy Queen and closing-prayer texts unmatched and "
              f"counted texts with no counterpart. The correct count is **{len(comparable) - len(identical)} of {len(comparable)}** differing, as listed here.", ""]
    counts: dict[str, int] = {}
    for prayer, language, held in comparable:
        for *_, kind in differences(held[0], prayer["english" if language == "en" else "latin"]):
            counts[kind] = counts.get(kind, 0) + 1
    lines += ["Differences by kind (individual word-level changes across all compared texts): " + "; ".join(f"{kind}: {n}" for kind, n in sorted(counts.items())) + ".", ""]
    lines += ["## Decisions needed from you", "",
              "1. **The I / J convention for Latin.** The document writes *Iesus*, *Iesum*, *Ioseph*; you authorized *Iesus → Jesus* for the Latin you supplied. Adopting the document's Latin reverses that for those prayers. Neither is wrong.",
              "2. **Which English edition the Rosary reader should use.** The held English is the only wording with a verified, cleared source (public-domain 19th- and early 20th-century books). The document's English is more modern but names no translator or source.",
              "3. **Whether to add the versicle and response** to the Hail Holy Queen, which only the document has.",
              "4. **Where the document came from.** Identifying its publisher would settle both its rights and which edition it follows (see the rights review).", ""]
    lines += ["## Prayer by prayer", ""]
    for prayer in DOC["prayers"]:
        key = prayer["key"]
        lines += [f"### {NAMES[key]}", ""]
        for language, field in (("en", "english"), ("la", "latin")):
            new = prayer[field]
            held = held_text(key, language)
            lines += [f"#### {LANGUAGE[language]}", ""]
            lines += [f"* **New:** {DOC['provenance']} (`{DOC['filename']}`), stored as `collection-{key}` ({LANGUAGE[language]}); rights unverified."]
            if held is None:
                lines += ["* **Existing:** none held. There is nothing to conflict with. The document's text is the only one, and it is unverified.", ""]
                continue
            old, source = held
            lines += [f"* **Existing:** {source}."]
            if old == new:
                lines += ["* **Result:** identical, character for character.", ""]
            else:
                diff = differences(old, new)
                structure = "same line structure" if old.count("\n") == new.count("\n") else f"line structure differs (held: {old.count(chr(10)) + 1} line(s), document: {new.count(chr(10)) + 1})"
                lines += [f"* **Layout:** {structure}.", "", "| Existing | Document | Kind |", "|---|---|---|"]
                lines += [f"| {cell(a)} | {cell(b)} | {kind} |" for a, b, kind in diff]
                lines += [""]
                if language == "la" and key in ORIGINAL and ORIGINAL[key] != old:
                    lines += ["*(The Latin supplied originally differed from the normalized text above in the authorized corrections only; see `docs/latin-normalization-diff.md`.)*", ""]
            kind, advice = ASSESSMENT[(key, language)]
            lines += [f"* **Nature of the difference:** {kind}", f"* **Recommendation:** {advice}", ""]
        if prayer["commentary_lines"]:
            lines += [f"*Document's own commentary kept with the text:* {' '.join(prayer['commentary_lines'])}", ""]
    lines += RIGHTS
    return "\n".join(lines).rstrip() + "\n"


RIGHTS = [
    "## Source and rights review of the imported prayers", "",
    "**What the document itself provides.** It names no author, translator, edition, publisher or licence. Its text mentions \"Orabimus\" "
    "(\"Orabimus provides audio narration of all prayers in seven languages\") and its link lines (\"Full page: …\") show it is an excerpt of a website's prayer page. "
    "That makes Orabimus a *plausible* publisher, but the document does not say so, and I have not checked the site. Nothing below is verified.", "",
    "Legend: **Verified**: a named source was checked and its rights established. **Plausible, unverified**: the document or the prayer's history suggests a source that has not been checked. **Unknown**: nothing identifies it.", "",
    "| Prayer | Latin text | English text | What the document says | Status |", "|---|---|---|---|---|",
    "| Sign of the Cross | Identical to a verified held source (Our Monthly Devotions, 1899, public domain). | Unknown translator; the held Baltimore wording is verified, this differs by one word. | Nothing about authorship. | Latin **verified by agreement** with the held source; English **unknown** |",
    "| Apostles' Creed | Unknown transcription. | Unknown; a modern hybrid wording, translator not named. | \"dating to the early centuries of the Church\". | **Unknown**; the prayer is ancient, the document's wording is not shown to be |",
    "| Our Father | Unknown transcription. | Unknown; a traditional form. | Cites Matthew 6:9-13 and Luke 11:2-4. | **Unknown** |",
    "| Hail Mary | Unknown transcription. | Unknown; traditional English. | Cites Luke 1:28 and 1:42; says Pius V fixed the form in the 1568 Roman Breviary. | **Plausible, unverified** history (Pius V / 1568 not checked); wording rights unknown |",
    "| Glory Be | Unknown transcription. | Unknown. | Nothing. | **Unknown** |",
    "| Fatima Prayer | No existing text; the document says the Latin versions are translations and that variants exist. | Unknown translation of a Portuguese original (1917). | Notes a variant (\"inferiori\") and names EWTN as preferring \"inferni\". | **Unknown**. A 20th-century prayer with several translations: rights are a real question |",
    "| Hail Holy Queen | Compare with Lings (1899) held, public domain. | Compare with Gahan (1844) held, public domain; the document's differs. | Says attributed to Hermann of Reichenau, origin uncertain. | Attribution **plausible, unverified**; the document's wording rights **unknown** |",
    "| Closing Prayer | No existing Latin. | A widely used translation; translator not named. | Nothing. | **Unknown** |",
    "| St. Michael Prayer | No existing Latin. | Common modern translation; the held Hammer (1909) is a different, verified one. | \"Composed by Pope Leo XIII in 1886\". | Attribution **plausible, unverified**; translation rights **unknown** |",
    "| Prayer to St. Joseph | No existing text. | Translator not named. | \"From Pope Leo XIII's encyclical *Quamquam Pluries* (1889)\". | Attribution **plausible, unverified**; the Latin is from a 19th-century papal document, but the English translation and this transcription are **unknown** |", "",
    "**Caution on rights.** That a Latin prayer is ancient does not make a particular English translation, or a particular modern transcription and punctuation, public domain. The document's English texts are "
    "therefore treated as **unknown**, and all twenty texts stay at rights `unverified` and status `proposed`. Not one can be verified or approved until you record a source and its rights. Nothing in this report changes any approval or publication status.", "",
    "**Held editions, for comparison.** *Verified*: Baltimore Catechism No. 1 (1885) and No. 3 (1921), Gahan's *Complete Manual of Catholic Piety* (1844), Lings' *Our Monthly Devotions* (1899) and Hammer's *General Catholic Devotions* (1909), each transcribed in Project Gutenberg and recorded with its source URL; "
    "*unverified*: the owner-supplied Latin file.", "",
]


if __name__ == "__main__":
    OUT.write_text(build(), encoding="utf-8")
    print(f"Wrote {OUT}")
