# ruff: noqa: E501
"""The traditional liturgical calendar: celebration, rank, season and a source-backed description, from the upstream engine (1960 Roman calendar)."""

import re
from datetime import date
from pathlib import Path

import pytest
from clerk_tokens import bearer
from fastapi.testclient import TestClient
from test_divine_office import CHECKOUT, PERL, PERL5LIB, needs_engine

from app.divine_office import calendar, engine
from app.divine_office.engine import EngineConfig, EngineUnavailable
from app.divine_office.names_en import translate
from app.divine_office.parser import parse

CONFIG = EngineConfig(CHECKOUT, PERL, PERL5LIB)


# ---- Pure helpers ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("english", "expected"), [
    ("St. Andrew Avellino Confessor", ("St. Andrew Avellino", "Confessor")),
    ("Sts. Peter and Paul, Apostles", ("Sts. Peter and Paul", "Apostles")),
    ("St. Matthias the Apostle", ("St. Matthias the Apostle", None)),                                    # "the Apostle" is part of the name, not cut off
    ("St. Joseph, Spouse of the Blessed Virgin Mary, Confessor", ("St. Joseph, Spouse of the Blessed Virgin Mary", "Confessor")),
    ("St. Francis de Sales Bishop, Confessor and Doctor of the Church", ("St. Francis de Sales", "Bishop, Confessor and Doctor of the Church")),
    ("St. Martin, Bishop of Tours, Confessor", ("St. Martin, Bishop of Tours", "Confessor")),
    ("St. Catherine of Siena Virgin", ("St. Catherine of Siena", "Virgin")),
    ("St. Agnes Virgin and Martyr", ("St. Agnes", "Virgin and Martyr")),
    ("St. Peter Martyr", ("St. Peter Martyr", None)),                                                     # a cognomen, not a classification
    ("St. Peter the Martyr", ("St. Peter the Martyr", None)),
    ("St. Stephen the First Martyr", ("St. Stephen, the First Martyr", None)),                           # the epithet stays with the name
    ("St. Stephen, the First Martyr", ("St. Stephen, the First Martyr", None)),
    ("Sts. Cosmas and Damian Martyrs", ("Sts. Cosmas and Damian Martyrs", None)),
    ("Seven Brothers, Martyrs, and Sts. Rufina and Secunda", ("Seven Brothers, Martyrs, and Sts. Rufina and Secunda", None)),
    ("Holy Innocents", ("Holy Innocents", None)),
    ("Assumption of the Blessed Virgin Mary", ("Assumption of the Blessed Virgin Mary", None)),
])
def test_the_engines_english_title_is_split_into_a_name_and_its_qualifier(english, expected):
    assert calendar.split_name(english) == expected


@pytest.mark.parametrize(("winner", "name", "kind"), [
    ("Sancti/11-10.txt", "S. Andreæ Avellini Confessoris", "saint"), ("Sancti/06-29.txt", "SS. Apostolorum Petri et Pauli", "saint"),
    ("Sancti/10-03.txt", "S. Teresiæ a Jesu Infante Virginis", "saint"),
    ("Sancti/08-15.txt", "In Assumptione Beatæ Mariæ Virginis", "feast"), ("Sancti/12-25.txt", "In Nativitate Domini", "feast"),
    ("Tempora/Epi5-0.txt", "Dominica V Post Epiphaniam III. Novembris", "sunday"), ("Tempora/Quad2-3.txt", "Feria Quarta infra Hebdomadam II in Quadragesima", "feria"),
    ("Tempora/Quad6-6.txt", "Sabbato Sancto", "feria"), ("Tempora/Pasc0-3.txt", "Die IV infra octavam Paschæ", "temporal"), ("Tempora/Pasc5-3.txt", "In Vigilia Ascensionis", "temporal"),
    ("Commune/C10b.txt", "Sanctæ Mariæ Sabbato", "other"),
])
def test_a_saint_a_feast_a_sunday_a_feria_and_a_temporal_celebration_are_told_apart(winner, name, kind):
    assert calendar.classify(winner, name) == kind


def test_the_rank_class_comes_from_the_engines_own_rank_text():
    assert [calendar.rank_class(t) for t in ("III. classis", "I. classis", "Dies Octavæ I. classis", "II. classis", "IV. classis", "Semiduplex", None)] == ["III", "I", "I", "II", "IV", None, None]


def test_sentences_do_not_break_after_abbreviations():
    assert calendar.sentences("Pope St. Leo wrote to Dr. Smith. He then died. Done.") == ["Pope St. Leo wrote to Dr. Smith.", "He then died.", "Done."]


def sentence(words):
    return " ".join(f"W{n}" for n in range(words)) + "."


def test_a_description_is_the_lessons_own_opening_sentences_in_35_to_65_words_verbatim():
    text = f"{sentence(15)} {sentence(18)} {sentence(29)} {sentence(40)}"
    picked = calendar.pick_description(text)
    assert picked == f"{sentence(15)} {sentence(18)} {sentence(29)}" and text.startswith(picked) and 35 <= len(picked.split()) <= 65
    assert calendar.pick_description(f"{sentence(20)} {sentence(20)} {sentence(40)}") == f"{sentence(20)} {sentence(20)}"            # two sentences are enough
    assert calendar.pick_description(f"{sentence(40)} {sentence(30)}") == sentence(40)                                                # a single sentence in range is kept whole, never cut
    assert calendar.pick_description(f"{sentence(10)} {sentence(10)} {sentence(10)} {sentence(10)}") is None                          # too short: nothing is padded
    assert calendar.pick_description(f"{sentence(80)} {sentence(10)}") is None                                                        # too long: nothing is trimmed mid-sentence
    assert calendar.pick_description(f"{sentence(30)} (omitted in the shorter form) {sentence(30)}") is None                           # the engine's markup for omissible text


def test_identity_tokens_ignore_titles_and_connectives():
    assert calendar.identity_tokens("St. Andrew Avellino Confessor") == ["Andrew", "Avellino"]


def test_only_a_lesson_that_follows_its_marker_directly_counts_as_a_biography():
    def office(lines_by_row):
        row = "<TR><TD>" + "<br/>".join(["x"] * len(lines_by_row)) + "</TD><TD>" + "<br/>".join(
            f"<FONT COLOR=\"red\"><I>{t}</I></FONT>" if kind == "rubric" else t for kind, t in lines_by_row) + "</TD></TR>"
        return parse(row)
    body = "Andrew was born at a village. " * 8
    assert calendar.legend_lesson(office([("text", "Reading 3"), ("text", body)])) == (body.strip(), 3)
    assert calendar.legend_lesson(office([("text", "Reading 3"), ("text", "From the Sermons of St. Leo"), ("text", body)])) is None       # a sermon has its source line first
    assert calendar.legend_lesson(office([("text", "Reading 4"), ("text", body)])) is None                                              # one nocturn: only Reading 3 qualifies
    assert calendar.legend_lesson(office([("rubric", "Nocturn II"), ("text", "Reading 4"), ("text", body)])) == (body.strip(), 4)         # three nocturns: Reading 4
    assert calendar.legend_lesson(office([("text", "Reading 3"), ("text", "short")])) is None


# ---- Against the upstream engine ----------------------------------------------------------------------------------------
@needs_engine
def test_10_november_2026_is_st_andrew_avellino_confessor_iii_class_with_a_verified_description():
    c = calendar.calendar(CONFIG, date(2026, 11, 10))
    assert (c.celebration, c.celebration_type, c.qualifier, c.rank, c.rank_class, c.rank_label) == ("St. Andrew Avellino", "saint", "Confessor", "III. classis", "III", "Confessor, III Class")
    assert c.celebration_latin == "S. Andreæ Avellini Confessoris" and c.edition == "roman_1960" and c.engine.version == "Rubrics 1960 - 1960" and len(c.engine.commit) == 40
    assert c.season == "Time after Pentecost (Sundays after Epiphany resumed)" and c.season_code == "Epi5"
    assert [x.latin for x in c.commemorations] == ["Commemoratio Ss. Tryphonis, Respicii, et Nymphæ Virg., Martyrum"] and "Commemoration" in c.commemorations[0].english
    assert c.description.text.startswith("Andrew Avellino, previously called Lancelot, was born at Castro Nuovo, a village in Lucania.")
    assert 35 <= len(c.description.text.split()) <= 65 and "Matins, Reading 3" in c.description.source.reference and "Sancti/11-10.txt" in c.description.source.reference
    raw = engine.run_engine(CONFIG, date(2026, 11, 10), "prayMatutinum")
    lesson = next(line.text for _, e in parse(raw).rows for line in e.lines if line.text.startswith("Andrew Avellino, previously called"))
    assert lesson.startswith(c.description.text) and len(lesson) > 3 * len(c.description.text) // 2          # a verbatim opening, not the whole lesson


@needs_engine
@pytest.mark.parametrize(("day", "kind", "name_part", "rank_class", "season"), [
    (date(2026, 8, 15), "feast", "Assumption of the Blessed Virgin Mary", "I", "Time after Pentecost"),
    (date(2026, 12, 25), "feast", "Nativity of Our Lord", "I", "Christmastide"),
    (date(2026, 11, 8), "sunday", "Fifth Sunday after Epiphany", "II", "Time after Pentecost (Sundays after Epiphany resumed)"),
    (date(2026, 3, 4), "feria", "Wednesday of the Second Week of Lent", "III", "Lent"),
    (date(2026, 4, 8), "temporal", "Fourth Day within the Octave of Easter", "I", "Eastertide"),
    (date(2026, 4, 15), "feria", "Wednesday of the First Week after the Octave of Easter", "IV", "Eastertide"),
    (date(2026, 1, 3), "other", "Our Lady’s Saturday", "IV", "Christmastide"),
])
def test_other_days_are_told_as_they_are_with_no_biography_invented(day, kind, name_part, rank_class, season):
    c = calendar.calendar(CONFIG, day)
    assert c.celebration_type == kind and c.celebration.startswith(name_part) and c.season == season and c.engine.version == "Rubrics 1960 - 1960"
    if rank_class:
        assert c.rank_class == rank_class
    assert c.description is None and c.qualifier is None                                                       # a feast, Sunday or feria is not a saint's biography


@needs_engine
def test_commemorations_are_reported_where_the_engine_gives_them():
    lent = calendar.calendar(CONFIG, date(2026, 3, 4))
    assert [c.latin for c in lent.commemorations] == ["Commemoratio S. Casimiri Confessoris", "Commemoratio S. Lucii I Papæ et Martyris"]
    assert calendar.calendar(CONFIG, date(2026, 8, 15)).commemorations == []


@needs_engine
@pytest.mark.parametrize("day", [date(2026, 1, 16), date(2026, 1, 29), date(2026, 4, 30), date(2026, 8, 12), date(2026, 8, 25), date(2026, 10, 16), date(2026, 11, 11), date(2026, 11, 24)])
def test_each_description_belongs_to_its_saint_and_is_taken_from_that_saints_own_lesson(day):
    c = calendar.calendar(CONFIG, day)
    assert c.celebration_type == "saint" and c.description is not None, day
    lesson = next(line.text for _, e in parse(engine.run_engine(CONFIG, day, "prayMatutinum")).rows for line in e.lines if line.text.startswith(c.description.text[:40]))
    assert lesson.startswith(c.description.text)                                                                  # verbatim, from the engine's own English Matins
    assert any(token.lower() in lesson.lower() for token in calendar.identity_tokens(c.celebration)), (day, c.celebration)
    assert 35 <= len(c.description.text.split()) <= 65 and c.description.source.name.startswith("The Roman Breviary") and "verbatim" in c.description.source.reference
    assert not re.search(r"[()&$~]", c.description.text)


@needs_engine
def test_days_without_a_reliable_lesson_show_the_celebration_without_a_description():
    for day in (date(2026, 6, 29), date(2026, 3, 19), date(2026, 12, 7), date(2026, 2, 24)):                       # 9-lesson sermons, and a saint whose lesson does not qualify
        c = calendar.calendar(CONFIG, day)
        assert c.celebration and c.rank_label and c.description is None, day


@needs_engine
def test_a_saint_whose_lesson_is_not_found_gets_no_description(monkeypatch):
    calendar._calendar.cache_clear()
    monkeypatch.setattr(calendar, "legend_lesson", lambda parsed: None)
    c = calendar.calendar(CONFIG, date(2026, 11, 10))
    assert c.celebration == "St. Andrew Avellino" and c.rank_label == "Confessor, III Class" and c.description is None
    calendar._calendar.cache_clear()


@needs_engine
def test_a_description_whose_lesson_does_not_mention_the_saint_is_refused(monkeypatch):
    calendar._calendar.cache_clear()
    monkeypatch.setattr(calendar, "legend_lesson", lambda parsed: (("He was born in a small town. " * 12).strip(), 3))
    assert calendar.calendar(CONFIG, date(2026, 11, 10)).description is None                                         # identity is checked, not assumed
    calendar._calendar.cache_clear()


# ---- The API --------------------------------------------------------------------------------------------------------------
@pytest.fixture
def engine_on(application):
    application.state.settings.divinum_officium_path = CHECKOUT
    application.state.settings.divinum_officium_perl = PERL
    application.state.settings.divinum_officium_perl5lib = PERL5LIB


def test_the_endpoint_needs_sign_in_validates_input_and_reports_an_unavailable_engine(application):
    assert TestClient(application, headers={}).get("/api/liturgical-calendar/2026-11-10").status_code == 401
    client = TestClient(application, headers=bearer("user_reader"))
    assert client.get("/api/liturgical-calendar/not-a-date").status_code == 422
    assert client.get("/api/liturgical-calendar/2026-11-10?edition=novus_ordo").status_code == 422                 # only the 1960 Roman calendar is offered
    application.state.settings.divinum_officium_path = None
    unavailable = client.get("/api/liturgical-calendar/2026-11-10")
    assert unavailable.status_code == 503 and "unavailable" in unavailable.json()["detail"] and "not configured" in unavailable.json()["detail"]


@needs_engine
def test_the_endpoint_returns_the_structured_calendar_and_caches_it(application, engine_on, monkeypatch):
    client = TestClient(application, headers=bearer("user_reader"))
    calendar._calendar.cache_clear()
    calls = []
    real = calendar.run_engine
    monkeypatch.setattr(calendar, "run_engine", lambda *args: calls.append(args) or real(*args))
    first = client.get("/api/liturgical-calendar/2026-11-10?edition=roman_1960")
    again = client.get("/api/liturgical-calendar/2026-11-10")
    assert first.status_code == 200 and again.json() == first.json() and len(calls) == 1                           # the Perl engine ran once for two requests
    body = first.json()
    assert (body["date"], body["edition"], body["celebration"], body["celebration_type"], body["rank"], body["rank_label"]) == ("2026-11-10", "roman_1960", "St. Andrew Avellino", "saint", "III. classis", "Confessor, III Class")
    assert {"season", "commemorations", "description", "engine"} <= set(body) and body["description"]["source"]["reference"] and body["engine"]["version"] == "Rubrics 1960 - 1960"
    assert client.get("/api/liturgical-calendar/2026-08-15").json()["description"] is None
    calendar._calendar.cache_clear()


def test_an_engine_answer_without_a_celebration_is_an_error_not_a_guess(monkeypatch):
    calendar._calendar.cache_clear()
    monkeypatch.setattr(calendar, "run_engine", lambda *args: "<TR><TD>x</TD><TD>y</TD></TR>\n<!--DO-META\tEpi5\tA day\twinner=Sancti/11-10.txt\tcommemoratio=\trank=3-->")
    with pytest.raises(EngineUnavailable):
        calendar.calendar(EngineConfig("unused"), date(2026, 11, 10))
    calendar._calendar.cache_clear()


# ---- English names -----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("latin", "english", "designation"), [
    ("Dominica V Post Epiphaniam", "Fifth Sunday after Epiphany", None),
    ("Dominica V Post Epiphaniam III. Novembris", "Fifth Sunday after Epiphany", "Third Sunday of November (Breviary numbering)"),
    ("Dominica XVII Post Pentecosten III. Septembris", "Seventeenth Sunday after Pentecost", "Third Sunday of September (Breviary numbering)"),
    ("Dominica XXIV et Ultima Post Pentecosten", "Twenty-fourth and Last Sunday after Pentecost", None),
    ("Feria Tertia infra Hebdomadam XXIII post Octavam Pentecostes I. Novembris", "Tuesday of the Twenty-third Week after the Octave of Pentecost", "First Week of November (Breviary numbering)"),
    ("Dominica post Ascensionem", "Sunday after the Ascension", None),
    ("Dominica I Adventus", "First Sunday of Advent", None), ("Dominica III in Quadragesima", "Third Sunday of Lent", None), ("Dominica II Post Pascha", "Second Sunday after Easter", None),
    ("Dominica de Passione", "Passion Sunday", None), ("Dominica in Palmis", "Palm Sunday", None), ("Dominica Resurrectionis", "Easter Sunday", None), ("Dominica Pentecostes", "Pentecost Sunday", None),
    ("Feria Quarta", None, None),                                                                                                   # no season context: not translated by guessing
    ("Feria Quarta infra Hebdomadam II in Quadragesima", "Wednesday of the Second Week of Lent", None),
    ("Feria II infra Hebdomadam I Adventus", "Monday of the First Week of Advent", None),
    ("Feria VI infra Hebdomadam VI post Epiphaniam", "Friday of the Sixth Week after Epiphany", None),
    ("Feria sexta infra Hebdomadam VII post Octavam Pentecostes", "Friday of the Seventh Week after the Octave of Pentecost", None),
    ("Sabbato infra Hebdomadam II post Octavam Pentecostes", "Saturday of the Second Week after the Octave of Pentecost", None),
    ("Feria IV Cinerum", "Ash Wednesday", None), ("Feria Quinta in Cena Domini", "Holy Thursday", None), ("Feria Sexta in Parasceve", "Good Friday", None), ("Sabbato Sancto", "Holy Saturday", None),
    ("Feria Quarta Quattuor Temporum Septembris", "Ember Wednesday of September", None),
    ("Die IV infra octavam Paschæ", "Fourth Day within the Octave of Easter", None), ("Diei II infra Octavam Nativitatis", "Second Day within the Octave of the Nativity", None),
    ("In Vigilia Ascensionis", "Vigil of the Ascension", None), ("In Vigilia Pentecostes", "Vigil of Pentecost", None), ("In Octava Ascensionis", "Octave Day of the Ascension", None),
    ("Feria Secunda in Rogationibus", "Rogation Monday", None),
])
def test_temporal_titles_are_translated_by_fixed_rules_or_not_at_all(latin, english, designation):
    assert translate(latin) == ((english, designation) if english else None)


def test_a_title_no_rule_matches_exactly_is_not_translated_and_an_unknown_designation_is_refused():
    for latin in ("Feria Nova infra Hebdomadam II in Quadragesima", "Dominica V Post Epiphaniam III. Martii", "Dominica XXX Post Pentecosten", "Patrocinii St. Joseph Confessoris Sponsi B.M.V. Confessoris", "Something Else Entirely"):
        assert translate(latin) is None, latin


@needs_engine
def test_every_temporal_title_in_the_upstream_data_translates_except_the_two_named_here():
    import glob
    untranslated = set()
    for path in glob.glob(str(Path(CHECKOUT) / "web/www/horas/Latin/Tempora/*.txt")):
        lines = Path(path).read_text(encoding="utf-8", errors="replace").split("\n")
        if lines[0].strip() == "[Officium]" and len(lines) > 1 and not lines[1].startswith("Ad Rom") and translate(lines[1].strip()) is None:
            untranslated.add(lines[1].strip())
    assert untranslated == {"In Octava Patrocinii S. Joseph", "Patrocinii St. Joseph Confessoris Sponsi B.M.V. Confessoris"}       # flagged in the report, not guessed


@needs_engine
@pytest.mark.parametrize(("day", "english", "latin", "source", "qualifier", "rank_label", "designation"), [
    (date(2026, 11, 10), "St. Andrew Avellino", "S. Andreæ Avellini Confessoris", "upstream_english", "Confessor", "Confessor, III Class", None),
    (date(2026, 12, 25), "Nativity of Our Lord Jesus Christ", "In Nativitate Domini", "upstream_english", None, "I Class", None),
    (date(2026, 12, 26), "St. Stephen, the First Martyr", "S. Stephani Protomartyris", "upstream_english", None, "II Class", None),
    (date(2026, 4, 29), "St. Peter the Martyr", "S. Petri Martyris", "upstream_english", None, "III Class", None),
    (date(2026, 6, 29), "Sts. Peter and Paul", "SS. Apostolorum Petri et Pauli", "upstream_english", "Apostles", "Apostles, I Class", None),
    (date(2026, 1, 21), "St. Agnes", "S. Agnetis Virginis et Martyris", "upstream_english", "Virgin and Martyr", "Virgin and Martyr, III Class", None),
    (date(2026, 2, 24), "St. Matthias the Apostle", "S. Matthiæ Apostoli", "upstream_english", None, "II Class", None),
    (date(2026, 11, 8), "Fifth Sunday after Epiphany", "Dominica V Post Epiphaniam III. Novembris", "translated", None, "II Class", "Third Sunday of November (Breviary numbering)"),
    (date(2026, 6, 21), "Fourth Sunday after Pentecost", "Dominica IV Post Pentecosten", "translated", None, "II Class", None),
    (date(2026, 12, 20), "Fourth Sunday of Advent", "Dominica IV Adventus", "translated", None, "I Class", None),
    (date(2026, 3, 8), "Third Sunday of Lent", "Dominica III in Quadragesima", "translated", None, "I Class", None),
    (date(2026, 3, 4), "Wednesday of the Second Week of Lent", "Feria Quarta infra Hebdomadam II in Quadragesima", "translated", None, "III Class", None),
    (date(2026, 4, 8), "Fourth Day within the Octave of Easter", "Die IV infra octavam Paschæ", "translated", None, "I Class", None),
    (date(2026, 5, 13), "Vigil of the Ascension", "In Vigilia Ascensionis", "translated", None, "II Class", None),
    (date(2026, 11, 3), "Tuesday of the Twenty-third Week after the Octave of Pentecost", "Feria Tertia infra Hebdomadam XXIII post Octavam Pentecostes I. Novembris", "translated", None, "IV Class", "First Week of November (Breviary numbering)"),
])
def test_english_names_keep_the_latin_and_say_where_the_name_came_from(day, english, latin, source, qualifier, rank_label, designation):
    c = calendar.calendar(CONFIG, day)
    assert (c.celebration, c.celebration_latin, c.celebration_source, c.qualifier, c.rank_label, c.designation) == (english, latin, source, qualifier, rank_label, designation)
    assert c.engine.version == "Rubrics 1960 - 1960" and c.edition == "roman_1960"


@needs_engine
def test_a_year_of_names_never_loses_part_of_a_saints_title_and_every_untranslated_one_is_flagged():
    from datetime import timedelta
    untranslated = []
    day = date(2026, 1, 1)
    while day <= date(2026, 12, 31):
        c = calendar.calendar(CONFIG, day)
        if c.celebration_source == "latin_untranslated":
            untranslated.append(c.celebration_latin)
        elif c.celebration_type == "saint":
            assert not c.celebration.endswith((" the", " of", " and")) and c.celebration.strip(", ") == c.celebration, c.celebration       # no dangling article from a cut
        day += timedelta(days=17)
    assert untranslated == [], untranslated


@pytest.mark.parametrize(("latin", "english"), [
    ("Dominica I Passionis", "Passion Sunday"), ("Dominica II Passionis seu in Palmis", "Palm Sunday"), ("Feria Secunda Hebdomadæ Sanctæ", "Monday of Holy Week"),
    ("Feria Sexta in Passione et Morte Domini", "Good Friday"), ("Die Secunda Januarii", "January 2"), ("Feria VI infra Hebdomadam post Ascensionem", "Friday in the week after the Ascension"),
    ("Sabbato in Vigilia Pentecostes", "Saturday, Vigil of Pentecost"), ("Die Quinta infra octavam Pentecostes", "Fifth Day within the Octave of Pentecost"),
    ("Feria IV Quattuor Temporum Adventus", "Ember Wednesday of Advent"), ("Sabbato Quattuor Temporum Adventus", "Ember Saturday of Advent"),
])
def test_the_titles_found_untranslated_in_the_full_year_scan_are_now_covered_by_exact_rules(latin, english):
    assert translate(latin) == (english, None)
