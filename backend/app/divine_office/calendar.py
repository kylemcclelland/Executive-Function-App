# ruff: noqa: E501
"""The principal celebration of a date in the 1960 Roman calendar, from the upstream engine, with a short source-backed description.

Nothing is calculated here. The celebration, its rank, the season and the winning office come from the Divinum Officium engine
(version "Rubrics 1960 - 1960"). A description is offered only for a saint's feast, and only when the engine's own English Matins
reading for that saint is a biographical lesson that can be attributed to this celebration; it is the lesson's own opening
sentences, copied verbatim. For Sundays, ferias, temporal feasts and feasts of the Lord or Our Lady no description is offered: the
engine's lessons for them are Scripture or homilies, not descriptions, and no other verified source is held.
"""

import re
from datetime import date
from functools import lru_cache

from pydantic import BaseModel

from . import service
from .engine import (
    UPSTREAM_URL,
    VERSION,
    EngineConfig,
    EngineUnavailable,
    run_engine,
    upstream_commit,
)
from .names_en import translate
from .parser import parse, parse_head

EDITION = "roman_1960"
# Exact corrections of upstream's English titles, keyed on the winning office file AND the exact upstream text, so nothing else can match.
# 14 April (Sancti/04-14.txt, St. Justin, Martyr) is titled "St. Justini Martyr" upstream: a Latin genitive in an English title.
ENGLISH_CORRECTIONS = {("Sancti/04-14.txt", "St. Justini Martyr"): "St. Justin Martyr"}
WINNER = re.compile(r"^(Sancti|Tempora|Commune)/[\w\-]+\.txt$")
FEAST_WORDS = re.compile(
    r"Mari[æa]e? Virginis|Domini|Crucis|Nativitat|Epiphani|Circumcision|Purificatio|Annuntiatio|Assumptio|Immaculat|Conceptio|"
    r"Transfiguratio|Dedicatio|Corporis|Sanguinis|Cordis|Nomin|Christi Regis|Trinitat|Angelorum|Omnium Sanctorum|Defunctorum|Sanctæ Familiæ",
)
_Q = r"(?:Bishop|Pope|Abbot|Confessor|Martyrs?|Virgins?|Widow|Matron|Doctor|Apostles?|Evangelist|Priest|Deacon|Monk|Hermit)"
_C = r"(?:and|of|the|Church|Doctor)"
QUALIFIER = re.compile(rf"^(?P<name>.+?)[,\s]+(?P<qualifier>{_Q}(?:[,\s]+(?:{_Q}|{_C}))*)\s*$")
TITLES = {"st", "ss", "saint", "saints", "blessed", "bl", "the", "of", "and", "de", "di", "pope", "bishop", "martyr", "martyrs", "confessor", "virgin", "abbot", "doctor", "widow", "apostle", "apostles", "evangelist", "priest"}
ABBREVIATIONS = {"St", "Ss", "Sts", "Mr", "Mrs", "Dr", "Bl", "No", "Vol", "Cap", "Ch", "Pope", "Fr", "Jr", "Sr", "etc", "i.e", "e.g", "viz", "cf"}
MIN_WORDS, MAX_WORDS = 35, 65


class SourceRef(BaseModel):
    name: str
    reference: str
    note: str


class Description(BaseModel):
    text: str
    source: SourceRef


class Commemoration(BaseModel):
    latin: str
    english: str | None


class EngineOut(BaseModel):
    name: str
    url: str
    commit: str | None
    version: str


class CalendarOut(BaseModel):
    date: date
    edition: str
    celebration: str
    celebration_latin: str
    celebration_source: str        # upstream_english | translated | latin_untranslated
    english_correction: str | None  # set when upstream's own English title was corrected (exact match only)
    designation: str | None        # e.g. "Third Sunday of November" for a resumed Epiphany Sunday
    celebration_type: str          # saint | feast | sunday | feria | temporal | other
    type_label: str
    qualifier: str | None          # for a saint: "Confessor", "Martyr", ... as the engine's English title gives it
    rank: str | None               # the engine's own text, e.g. "III. classis"
    rank_class: str | None         # "I", "II", "III" or "IV" when the engine's rank names a class
    rank_label: str | None         # ready to display, e.g. "Confessor, III Class"
    season: str | None
    season_code: str | None
    commemorations: list[Commemoration]
    description: Description | None
    engine: EngineOut


EPITHETS = [(re.compile(r"(?<!,)\s+(the First Martyr)$"), r", \1")]      # an epithet that belongs to the name: "St. Stephen, the First Martyr"
_QUALIFIER_LIST = rf"{_Q}(?:[,\s]+(?:{_Q}|{_C}))*"
NOT_A_BOUNDARY = {"the", "of", "and", "first", "second", "de", "di"}


def split_name(english: str) -> tuple[str, str | None]:
    """The saint's name and, only when the boundary is unambiguous, the qualifier ("Confessor", "Bishop and Doctor of the Church").

    Split when a comma sets the qualifier apart ("Sts. Peter and Paul, Apostles"), or when a state-of-life qualifier (not "Martyr", which also occurs in
    names such as "St. Peter Martyr") follows a name that does not end in an article, "of" or an ordinal ("St. Andrew Avellino Confessor"). Otherwise the whole
    title is kept as the name: nothing is ever cut out of it.
    """
    text = english.strip()
    for pattern, replacement in EPITHETS:
        text = pattern.sub(replacement, text)
    # The earliest point where what follows is nothing but a qualifier. A comma makes it unambiguous; without one, "Martyr" is never split off
    # (it can be a cognomen), and neither is a qualifier after "the", "of" or an ordinal ("St. Matthias the Apostle").
    for found in re.finditer(rf"(?P<comma>,\s+|\s+)(?P<qualifier>{_QUALIFIER_LIST})$", text):
        name = text[:found.start()].strip()
        if not name:
            continue
        if "," in found.group("comma") or (not re.match(r"Martyrs?\b", found.group("qualifier")) and name.split()[-1].lower() not in NOT_A_BOUNDARY):
            return name, found.group("qualifier").strip()
    return text, None


def classify(winner: str, name_latin: str) -> str:
    if winner.startswith("Tempora/"):
        if name_latin.startswith("Dominica"):
            return "sunday"
        if name_latin.startswith(("Feria", "Sabbato")):
            return "feria"
        return "temporal"
    if winner.startswith("Sancti/"):
        if FEAST_WORDS.search(name_latin):
            return "feast"
        return "saint" if re.match(r"^(S\.|SS\.|Ss\.|B\.|Ss\b)", name_latin) else "feast"
    return "other"


def rank_class(rank_text: str | None) -> str | None:
    found = re.search(r"\b(IV|III|II|I)\.?\s+[Cc]lassis\b", rank_text or "")
    return found.group(1) if found else None


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z“\"‘'])", text.strip())
    merged: list[str] = []
    for part in parts:
        if merged and merged[-1].rstrip(".").split(" ")[-1].rstrip(".") in ABBREVIATIONS:
            merged[-1] += " " + part
        else:
            merged.append(part)
    return merged


def pick_description(text: str) -> str | None:
    """The lesson's own opening sentences (2 or 3 when possible), 35 to 65 words, verbatim; None if no such stretch exists."""
    if re.search(r"[()&$~]", text[:900]):           # the engine's markup for omissible text: not a clean passage
        return None
    chosen: list[str] = []
    for sentence in sentences(text)[:3]:
        chosen.append(sentence)
        words = len(" ".join(chosen).split())
        if len(chosen) >= 2 and MIN_WORDS <= words <= MAX_WORDS:
            return " ".join(chosen)
        if words > MAX_WORDS:
            break
    one = sentences(text)[:1]
    if one and MIN_WORDS <= len(one[0].split()) <= MAX_WORDS:
        return one[0]
    return None


def identity_tokens(english_name: str) -> list[str]:
    return [word for word in re.findall(r"[A-Za-z]{4,}", english_name) if word.lower() not in TITLES]


def legend_lesson(parsed) -> tuple[str, int] | None:
    """The saint's own biographical lesson in the engine's English Matins: Reading 3 of a one-nocturn Office, Reading 4 of a three-nocturn one.

    It qualifies only if the body follows the "Reading N" marker directly (a Scripture lesson or a sermon has a source line first).
    """
    english_rubrics = [line.text for _, e in parsed.rows for line in e.lines if line.kind == "rubric"]
    wanted = 4 if "Nocturn II" in english_rubrics else 3
    for _, english in parsed.rows:
        for index, line in enumerate(english.lines[:-1]):
            if line.kind == "text" and line.text == f"Reading {wanted}":
                body = english.lines[index + 1]
                if body.kind == "text" and len(body.text) >= 150:
                    return body.text, wanted
    return None


def lent_aware_season(code: str | None, name_latin: str, day: date) -> str | None:
    """The season label for the engine's season code, except that Ash Wednesday and the days after it are Lent.

    The engine's code for the Sunday of Quinquagesima week runs on through the Saturday after Ash Wednesday ("Quadp3"); its own titles for those days
    ("Feria IV Cinerum", "Feria V post Cineres", "Sabbato post Cineres") say they belong to Lent. Nothing is calculated: the engine's title decides.
    """
    if code and code.startswith("Quadp") and re.search(r"Cinerum$|post Cineres", name_latin.strip()):
        return "Lent"
    return service.season_label(code or "", day)


@lru_cache(maxsize=400)
def _calendar(config: EngineConfig, day: date) -> CalendarOut:
    raw = run_engine(config, day, "prayMatutinum")
    parsed = parse(raw)
    head = parse_head(raw)
    winner = parsed.meta.get("winner", "")
    if not head.get("name_latin") or not WINNER.match(winner):
        raise EngineUnavailable("The engine did not return a celebration for this date.")
    kind = classify(winner, head["name_latin"])
    english = head.get("name_english") or ""
    correction = None
    if (winner, english) in ENGLISH_CORRECTIONS:
        correction = f"Upstream's English title “{english}” was corrected to “{ENGLISH_CORRECTIONS[(winner, english)]}”"
        english = ENGLISH_CORRECTIONS[(winner, english)]
    qualifier = None
    designation = None
    if winner.startswith("Tempora/") or not english:
        # Upstream's English "Tempora" titles are Latin: use the deterministic, tested translation; keep the Latin (and flag it) if no rule matches.
        translated = translate(head["name_latin"])
        name, designation = translated if translated else (head["name_latin"], None)
        source = "translated" if translated else "latin_untranslated"
    else:
        english = re.sub(r"^(?:SS|Ss)\.\s", "Sts. ", re.sub(r"^S\.\s", "St. ", english))      # upstream's English titles sometimes keep the Latin abbreviation
        name, qualifier = split_name(english) if kind == "saint" else (english, None)
        source = "upstream_english"
    rank_text = head.get("rank_text") or None
    klass = rank_class(rank_text)
    class_label = f"{klass} Class" if klass else None
    rank_label = ", ".join(part for part in (qualifier, class_label) if part) or rank_text
    description = None
    if kind == "saint" and english:
        lesson = legend_lesson(parsed)
        if lesson:
            text, number = lesson
            tokens = identity_tokens(english)
            picked = pick_description(text)
            if picked and tokens and any(token.lower() in text.lower() for token in tokens):
                description = Description(text=picked, source=SourceRef(
                    name="The Roman Breviary, Matins lesson (English), as supplied by Divinum Officium",
                    reference=f"Matins, Reading {number}, {english} ({winner}); the lesson's opening sentences, verbatim",
                    note="Translation rights are not verified; see docs/divine-office.md",
                ))
    commemorations: list[Commemoration] = []
    try:
        lauds = service.office(config, day, "lauds")
        commemorations = [Commemoration(latin=m.latin, english=m.english) for s in lauds.sections for r in s.rows for m in r.marks if m.kind == "commemoration"]
    except EngineUnavailable:
        pass
    code = parsed.meta.get("season_code") or None
    return CalendarOut(
        date=day, edition=EDITION, celebration=name, celebration_latin=head["name_latin"], celebration_source=source, english_correction=correction, designation=designation, celebration_type=kind,
        type_label={"saint": "Saint", "feast": "Feast", "sunday": "Sunday", "feria": "Feria", "temporal": "Temporal feast"}.get(kind, "Celebration"),
        qualifier=qualifier, rank=rank_text, rank_class=klass, rank_label=rank_label, season=lent_aware_season(code, head["name_latin"], day), season_code=code,
        commemorations=commemorations, description=description,
        engine=EngineOut(name="Divinum Officium", url=UPSTREAM_URL, commit=upstream_commit(config.path) if config.path else None, version=VERSION),
    )


def calendar(config: EngineConfig, day: date) -> CalendarOut:
    return _calendar(config, day)
