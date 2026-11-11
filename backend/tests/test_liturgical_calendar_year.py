# ruff: noqa: E501
"""Validation of every day of 2026 (set OPTIMA_FULL_YEAR=1; it runs the Perl engine for each date, about 8 minutes) and of the Patronage of St. Joseph exception.

Two kinds of check, kept apart on purpose:
  * faithful handling of the engine's output: every day resolves, names are well formed, the Latin is kept, the rank, season and commemorations are the engine's;
  * independent checks that do not rely on the Perl engine's own logic: the dates of Easter-based feasts computed here by the Gauss/anonymous computus, the weekday named in a
    feria's English title against the actual weekday, the Sundays, Ember days and the Lent/Advent boundaries. These show the engine's answers are consistent with the
    calendar's arithmetic. They are NOT a comparison with a printed 1960 Breviary or Ordo, which has not been done.
"""

import os
import re
from datetime import date, timedelta

import pytest
from test_divine_office import CHECKOUT, PERL, PERL5LIB, needs_engine

from app.divine_office import calendar, service
from app.divine_office.engine import EngineConfig, EngineUnavailable

CONFIG = EngineConfig(CHECKOUT, PERL, PERL5LIB)
FULL_YEAR = pytest.mark.skipif(not os.environ.get("OPTIMA_FULL_YEAR"), reason="runs the engine for all 365 days: set OPTIMA_FULL_YEAR=1")
YEAR = 2026
# The saints of 2026 whose Matins lesson does not qualify as a biography (found by the earlier full-year scan). The 14 April entry is no longer here: correcting
# the upstream title "St. Justini Martyr" to "St. Justin Martyr" lets the identity check match that saint's own lesson.
WITHOUT_DESCRIPTION = {
    "2026-01-21", "2026-01-24", "2026-01-26", "2026-02-06", "2026-02-24", "2026-03-19", "2026-04-13", "2026-04-25", "2026-05-01", "2026-05-07", "2026-06-29", "2026-07-03", "2026-07-10",
    "2026-07-22", "2026-08-08", "2026-08-10", "2026-08-27", "2026-10-08", "2026-10-09", "2026-10-20", "2026-10-24", "2026-11-30", "2026-12-07", "2026-12-26", "2026-12-28",
}
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def easter(year: int) -> date:
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    el = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * el) // 451
    month, day = divmod(h + el - 7 * m + 114, 31)
    return date(year, month, day + 1)


def advent_sunday_1(year: int) -> date:
    christmas = date(year, 12, 25)
    return christmas - timedelta(days=(christmas.isoweekday() % 7 or 7) + 21)


def third_sunday_of_september(year: int) -> date:
    """The third civil Sunday of September: under the 1960 rubrics the liturgical month begins with its first Sunday (the engine's "modern style" count)."""
    first = date(year, 9, 1)
    return first + timedelta(days=(6 - first.weekday()) % 7 + 14)


def ember_wednesdays(year: int) -> list[date]:
    """1960 Ember seasons: after the 1st Sunday of Lent, after Pentecost, after the 3rd Sunday of September, after the 3rd Sunday of Advent."""
    e = easter(year)
    return [e - timedelta(days=42) + timedelta(days=3), e + timedelta(days=49) + timedelta(days=3), third_sunday_of_september(year) + timedelta(days=3), advent_sunday_1(year) + timedelta(days=14 + 3)]


def ember_dates(year: int) -> set[date]:
    return {wednesday + timedelta(days=offset) for wednesday in ember_wednesdays(year) for offset in (0, 2, 3)}


def anchors(year: int) -> dict[date, str]:
    """Celebrations whose dates follow from Easter or the fixed calendar, with a word their English name must contain."""
    e = easter(year)
    return {
        e: "Easter Sunday", e - timedelta(days=46): "Ash Wednesday", e - timedelta(days=14): "Passion Sunday", e - timedelta(days=7): "Palm Sunday", e - timedelta(days=3): "Holy Thursday",
        e - timedelta(days=2): "Good Friday", e - timedelta(days=1): "Holy Saturday", e + timedelta(days=39): "Ascension", e + timedelta(days=49): "Pentecost", e + timedelta(days=56): "Trinity",
        e + timedelta(days=60): "Corpus Christi", advent_sunday_1(year): "First Sunday of Advent", date(year, 12, 25): "Nativity", date(year, 1, 6): "Epiphany", date(year, 2, 2): "Purification",
        date(year, 3, 25): "Annunciation", date(year, 8, 15): "Assumption", date(year, 12, 8): "Immaculate Conception", date(year, 11, 1): "All Saints", date(year, 11, 2): "All Souls",
        date(year, 6, 24): "John the Baptist", date(year, 3, 19): "Joseph", date(year, 6, 29): "Peter",
    }


def check_well_formed(c) -> list[str]:
    problems = []
    name = c.celebration
    if not name or name != name.strip() or "  " in name or name.strip(",; ") != name or re.search(r"\b(None|null)\b|;", name):
        problems.append(f"malformed name {name!r}")
    if name.endswith((" the", " of", " and")):
        problems.append(f"dangling word in {name!r}")
    if not c.celebration_latin or c.celebration_latin != c.celebration_latin.strip():
        problems.append("missing or malformed Latin")
    if c.celebration_source not in {"upstream_english", "translated", "latin_untranslated"}:
        problems.append(f"unknown source {c.celebration_source}")
    flat = lambda text: re.sub(r"\s+", "", text.replace("æ", "ae")).lower()  # noqa: E731
    if c.celebration_source == "upstream_english" and flat(c.celebration) == flat(c.celebration_latin):
        problems.append(f"the 'English' title is the Latin: {c.celebration!r}")
    if c.celebration_source == "translated" and c.celebration == c.celebration_latin:
        problems.append("marked translated but identical to the Latin")
    if c.celebration_source == "latin_untranslated" and c.celebration != c.celebration_latin:
        problems.append("untranslated but differs from the Latin")
    if not c.rank or not c.rank_label or c.rank_class not in {"I", "II", "III", "IV", None}:
        problems.append(f"rank {c.rank!r}/{c.rank_label!r}/{c.rank_class!r}")
    if not c.season_code or not c.season or c.season != service.season_label(c.season_code, c.date):
        problems.append(f"season {c.season_code!r}/{c.season!r}")
    if c.edition != "roman_1960" or c.engine.version != "Rubrics 1960 - 1960":
        problems.append("wrong edition or version")
    if c.celebration_type not in {"saint", "feast", "sunday", "feria", "temporal", "other"}:
        problems.append("unknown type")
    if any(not m.latin.startswith("Commemoratio") for m in c.commemorations) or len({m.latin for m in c.commemorations}) != len(c.commemorations):
        problems.append("commemoration malformed or duplicated")
    if c.description and (c.celebration_type != "saint" or not 35 <= len(c.description.text.split()) <= 65 or not c.description.source.reference or "verbatim" not in c.description.source.reference):
        problems.append("description not a short verbatim saint's lesson")
    if c.designation and "(Breviary numbering)" not in c.designation:
        problems.append("designation without the Breviary-numbering qualifier")
    return problems


@needs_engine
@FULL_YEAR
def test_every_day_of_2026_resolves_and_agrees_with_independent_calendar_arithmetic():
    days = {}
    day = date(YEAR, 1, 1)
    while day.year == YEAR:
        for attempt in (1, 2):                                                       # one retry: a stalled Perl start-up (for example after the machine slept) is not a calendar error
            try:
                days[day] = calendar.calendar(CONFIG, day)
                break
            except EngineUnavailable:
                if attempt == 2:
                    raise
        day += timedelta(days=1)
    errors = []

    def check(condition, message):
        if not condition:
            errors.append(str(message))

    assert len(days) == 365
    # ---- faithful handling: every day, well formed ----
    problems = {str(d): p for d, c in days.items() if (p := check_well_formed(c))}
    assert not problems, problems
    assert not [str(d) for d, c in days.items() if c.celebration_source == "latin_untranslated"], "untranslated titles remain"
    assert not [str(d) for d, c in days.items() if c.english_correction and (d != date(YEAR, 4, 14))]            # the only corrected title is the one named
    # ---- saint descriptions preserved ----
    saints = {str(d): c for d, c in days.items() if c.celebration_type == "saint"}
    assert len(saints) == 137
    without = {d for d, c in saints.items() if c.description is None}
    check(without == WITHOUT_DESCRIPTION, (without ^ WITHOUT_DESCRIPTION))
    assert len(saints) - len(without) == 112
    # ---- independent arithmetic ----
    e = easter(YEAR)
    for when, word in anchors(YEAR).items():
        check(word in days[when].celebration, (when, word, days[when].celebration))
    advent1 = advent_sunday_1(YEAR)
    for when, c in days.items():
        weekday = WEEKDAYS[when.weekday()]
        first = c.celebration.split(" ")[0]
        if c.celebration_type == "feria" and first in WEEKDAYS:
            check(first == weekday, (when, c.celebration))                                                  # a feria's English title names the real weekday
        if c.celebration_type == "sunday" and " Sunday" in c.celebration:
            check(when.weekday() == 6, (when, c.celebration))
        if c.celebration_type == "sunday":
            check(c.celebration_latin.startswith("Dominica") and when.weekday() == 6, (when, c.celebration_latin))
        if when.weekday() == 6:
            check(c.celebration_type in {"sunday", "feast", "saint", "temporal", "other"}, (when, c.celebration_type))
    # Ember days (1960): Wednesday, Friday and Saturday after the 1st Sunday of Lent, Pentecost, the 3rd Sunday of September and the 3rd Sunday of Advent, and no others
    expected_ember = ember_dates(YEAR)
    for when in sorted(expected_ember):
        check("Ember" in days[when].celebration, (when, days[when].celebration))
    check(not [str(d) for d, c in days.items() if "Ember" in c.celebration and d not in expected_ember], "Ember on an unexpected date")
    # Lent, Septuagesima and Advent boundaries
    for when, c in days.items():
        if e - timedelta(days=46) <= when <= e - timedelta(days=1):
            check(c.season == "Lent", (when, c.season))
        elif e - timedelta(days=63) <= when < e - timedelta(days=46):
            check(c.season == "Septuagesima", (when, c.season))
        elif advent1 <= when <= date(YEAR, 12, 24):
            check(c.season == "Advent", (when, c.season))
        elif date(YEAR, 12, 25) <= when or when <= date(YEAR, 1, 5):
            check(c.season == "Christmastide", (when, c.season))
    # Resumed Sundays after Epiphany designate themselves as Breviary-numbered weeks of November, never as civil dates
    resumed = [(d, c) for d, c in days.items() if c.celebration_type == "sunday" and c.celebration.endswith("after Epiphany") and d.month >= 10]
    check(bool(resumed) and all(c.designation and c.designation.endswith("of November (Breviary numbering)") for _, c in resumed), "resumed Sundays lack the Breviary-numbering designation")
    assert not errors, errors[:40]
    # a quick summary for the report
    print("SUMMARY", {t: sum(1 for c in days.values() if c.celebration_type == t) for t in ("saint", "feast", "sunday", "feria", "temporal", "other")}, "sources", {s: sum(1 for c in days.values() if c.celebration_source == s) for s in ("upstream_english", "translated")}, "commemorations", sum(len(c.commemorations) for c in days.values()))


@needs_engine
def test_the_patronage_of_st_joseph_titles_never_occur_under_the_1960_rubrics_in_the_years_checked():
    """Their upstream [Rank] has no 1960 entry (the feast was suppressed in 1955); the engine gives the ordinary Wednesday of those weeks instead."""
    for year in range(2025, 2031):
        easter_day = easter(year)
        for weeks in (2, 3):
            wednesday = easter_day + timedelta(days=7 * weeks + 3)
            c = calendar.calendar(CONFIG, wednesday)
            assert "Patrocinii" not in c.celebration_latin and "Patronage" not in c.celebration and c.celebration_source != "latin_untranslated", (wednesday, c.celebration_latin)


def test_the_two_patronage_titles_stay_latin_and_untranslated_by_design():
    from app.divine_office.names_en import translate
    assert translate("In Octava Patrocinii S. Joseph") is None
    assert translate("Patrocinii St. Joseph Confessoris Sponsi B.M.V. Confessoris") is None


def test_only_the_exact_upstream_justin_title_is_corrected():
    assert calendar.ENGLISH_CORRECTIONS == {("Sancti/04-14.txt", "St. Justini Martyr"): "St. Justin Martyr"}
    assert calendar.split_name("St. Justin Martyr") == ("St. Justin Martyr", None)                                           # the cognomen-like "Martyr" is not split off


@needs_engine
def test_14_april_is_st_justin_martyr_with_the_latin_kept_and_the_correction_recorded():
    c = calendar.calendar(CONFIG, date(2026, 4, 14))
    assert (c.celebration, c.celebration_latin, c.celebration_source, c.rank_label) == ("St. Justin Martyr", "S. Justini Martyris", "upstream_english", "III Class")
    assert c.english_correction == "Upstream's English title “St. Justini Martyr” was corrected to “St. Justin Martyr”"
    assert c.description and c.description.text.startswith("Justin, son of Priscus") and "Sancti/04-14.txt" in c.description.source.reference
    assert calendar.calendar(CONFIG, date(2026, 4, 29)).english_correction is None and calendar.calendar(CONFIG, date(2026, 11, 10)).english_correction is None


@needs_engine
def test_the_weeks_of_november_use_the_breviarys_numbering_which_is_not_the_civil_count():
    sunday = calendar.calendar(CONFIG, date(2026, 11, 8))                       # the second Sunday of the civil month: the Breviary's III
    assert sunday.designation == "Third Sunday of November (Breviary numbering)" and date(2026, 11, 8).day // 7 == 1
    assert calendar.calendar(CONFIG, date(2026, 11, 3)).designation == "First Week of November (Breviary numbering)"
    assert "Fourth Sunday of November" in calendar.calendar(CONFIG, date(2026, 11, 15)).designation


# ---- Fast, deterministic: the arithmetic helpers (no engine) ------------------------------------------------------------------
def test_the_computus_matches_known_dates_of_easter():
    assert [easter(y) for y in (2024, 2025, 2026, 2027, 2028)] == [date(2024, 3, 31), date(2025, 4, 20), date(2026, 4, 5), date(2027, 3, 28), date(2028, 4, 16)]


def test_the_ember_days_of_2026_follow_the_1960_rule():
    assert sorted(ember_dates(2026)) == [
        date(2026, 2, 25), date(2026, 2, 27), date(2026, 2, 28),               # after the 1st Sunday of Lent (22 February)
        date(2026, 5, 27), date(2026, 5, 29), date(2026, 5, 30),               # after Pentecost (24 May)
        date(2026, 9, 23), date(2026, 9, 25), date(2026, 9, 26),               # after the 3rd Sunday of September (20 September), not after 14 September
        date(2026, 12, 16), date(2026, 12, 18), date(2026, 12, 19),            # after the 3rd Sunday of Advent (13 December)
    ]


@pytest.mark.parametrize("year", range(2024, 2032))
def test_the_ember_wednesdays_are_wednesdays_in_their_seasons_in_any_year(year):
    lent, pentecost, september, advent = ember_wednesdays(year)
    assert all(w.weekday() == 2 for w in (lent, pentecost, september, advent))
    assert third_sunday_of_september(year).weekday() == 6 and 15 <= third_sunday_of_september(year).day <= 21 and 16 <= september.day <= 24
    assert advent_sunday_1(year).weekday() == 6 and date(year, 11, 27) <= advent_sunday_1(year) <= date(year, 12, 3) and advent > advent_sunday_1(year) + timedelta(days=14)
    assert len(ember_dates(year)) == 12 and lent == easter(year) - timedelta(days=39) and pentecost == easter(year) + timedelta(days=52)


# ---- Bounded engine checks: only the dates that matter, not a year scan ----------------------------------------------------------
@needs_engine
def test_the_ember_days_in_lent_pentecost_september_and_advent_match_the_engine_and_no_nearby_day_is_ember():
    for when in sorted(ember_dates(2026)):
        c = calendar.calendar(CONFIG, when)
        assert "Ember" in c.celebration and "Quattuor Temporum" in c.celebration_latin and c.celebration_source == "translated", (when, c.celebration)
    for when in (date(2026, 9, 16), date(2026, 9, 18), date(2026, 9, 19), date(2026, 12, 9), date(2026, 12, 23), date(2026, 3, 4)):           # Sept 16/18/19 would be the pre-1960 (after 14 September) Ember days
        assert "Ember" not in calendar.calendar(CONFIG, when).celebration, when


@needs_engine
def test_the_easter_based_and_fixed_celebrations_of_2026_fall_on_the_dates_computed_independently():
    for when, word in anchors(2026).items():
        c = calendar.calendar(CONFIG, when)
        assert word in c.celebration, (when, word, c.celebration)
        assert c.engine.version == "Rubrics 1960 - 1960"


@needs_engine
def test_the_season_boundaries_of_2026_fall_where_the_calendar_arithmetic_puts_them():
    e = easter(2026)
    expected = {
        e - timedelta(days=64): "Time after Epiphany", e - timedelta(days=63): "Septuagesima", e - timedelta(days=47): "Septuagesima", e - timedelta(days=46): "Lent", e - timedelta(days=42): "Lent", e - timedelta(days=1): "Lent",
        advent_sunday_1(2026) - timedelta(days=1): None, advent_sunday_1(2026): "Advent", date(2026, 12, 24): "Advent", date(2026, 12, 25): "Christmastide", date(2026, 1, 5): "Christmastide",
    }
    for when, season in expected.items():
        got = calendar.calendar(CONFIG, when).season
        if season is not None:
            assert got == season, (when, got)


def test_ash_wednesday_and_the_days_after_it_are_lent_even_though_the_engines_code_is_still_quinquagesima_week():
    assert calendar.lent_aware_season("Quadp3", "Feria IV Cinerum", date(2026, 2, 18)) == "Lent"
    assert calendar.lent_aware_season("Quadp3", "Feria V post Cineres", date(2026, 2, 19)) == "Lent"
    assert calendar.lent_aware_season("Quadp3", "Sabbato post Cineres", date(2026, 2, 21)) == "Lent"
    assert calendar.lent_aware_season("Quadp3", "Dominica in Quinquagesima", date(2026, 2, 15)) == "Septuagesima"
    assert calendar.lent_aware_season("Quadp3", "Feria III infra Hebdomadam Quinquagesimæ", date(2026, 2, 17)) == "Septuagesima"
    assert calendar.lent_aware_season("Quad1", "Dominica I in Quadragesima", date(2026, 2, 22)) == "Lent"
    assert calendar.lent_aware_season(None, "x", date(2026, 2, 22)) is None


@needs_engine
def test_the_week_around_ash_wednesday_changes_season_on_ash_wednesday():
    seasons = {d: calendar.calendar(CONFIG, d).season for d in (date(2026, 2, 15), date(2026, 2, 17), date(2026, 2, 18), date(2026, 2, 21), date(2026, 2, 22))}
    assert seasons == {date(2026, 2, 15): "Septuagesima", date(2026, 2, 17): "Septuagesima", date(2026, 2, 18): "Lent", date(2026, 2, 21): "Lent", date(2026, 2, 22): "Lent"}

