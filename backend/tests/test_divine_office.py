# ruff: noqa: E501
"""The Divine Office module: the parser on synthetic markup, and (when a Divinum Officium checkout is available) Compline for
contrasting dates checked against the upstream engine's own output. Nothing here is real liturgical text except what the engine returns."""

import os
import re
from datetime import date
from pathlib import Path

import pytest
from clerk_tokens import bearer
from fastapi.testclient import TestClient

from app.divine_office import engine, parser, service
from app.divine_office.engine import EngineConfig, EngineUnavailable

LOCAL = Path("C:/Users/uvaga/divinum-officium")
CHECKOUT = os.environ.get("DIVINUM_OFFICIUM_PATH") or (str(LOCAL) if LOCAL.is_dir() else None)
PERL5LIB = os.environ.get("DIVINUM_OFFICIUM_PERL5LIB") or ("/c/Users/uvaga/divinum-officium-perl5lib" if CHECKOUT == str(LOCAL) else None)
PERL = os.environ.get("DIVINUM_OFFICIUM_PERL") or ("C:/Program Files/Git/usr/bin/perl.exe" if Path("C:/Program Files/Git/usr/bin/perl.exe").exists() else "perl")
CONFIG = EngineConfig(CHECKOUT, PERL, PERL5LIB)
needs_engine = pytest.mark.skipif(not CHECKOUT, reason="no Divinum Officium checkout (set DIVINUM_OFFICIUM_PATH)")

ROW = (
    "<TR><TD VALIGN='TOP' ID='X1'><DIV ALIGN='right'><FONT SIZE='1' COLOR='green'><A HREF='#top'>Top</A></FONT></DIV>\n"
    "<FONT SIZE='+1' COLOR=\"red\"><B><I>Psalmi</I></B></FONT> <FONT SIZE='-1' >{ex Psalterio}</FONT>\n<br/>\n"
    "<FONT COLOR=\"red\"><I>Ant.</I></FONT> Filler antiphon.<br/>\n<FONT COLOR=\"red\"><I>Psalmus 4</I></FONT><FONT SIZE='-1' > [1]</FONT><br/>\n"
    "<FONT SIZE='1' COLOR=\"red\">4:2</FONT> Filler verse &amp; more.<br/>\n<FONT COLOR=\"red\"><I>&#8483;.</I></FONT> Filler versicle<br/>\n"
    "<FONT SIZE='1' COLOR=\"red\">A whole red rubric.</FONT><br/>\n<FONT SIZE='+2' COLOR=\"red\"><B><I>P</I></B></FONT>lain text.<br/>\n</TD>\n"
    "<TD VALIGN='TOP'><FONT SIZE='+1' COLOR=\"red\"><B><I>Psalms</I></B></FONT>\n<br/>\n<FONT COLOR=\"red\"><I>Ant.</I></FONT> English filler.<br/>\n</TD>\n</TR>\n"
)


# ---- The parser, on synthetic markup ------------------------------------------------------------------------------
def test_the_parser_labels_each_line_from_the_engines_own_markup_and_copies_the_words():
    (latin, english), = parser.parse("<P ALIGN=CENTER><FONT >Title ~ I. classis</FONT></P>" + ROW).rows
    assert (latin.heading, latin.note, english.heading) == ("Psalmi", "{ex Psalterio}", "Psalms")
    assert [(line.kind, line.label, line.text) for line in latin.lines] == [
        ("antiphon", "Ant.", "Filler antiphon."), ("psalm_heading", "Psalmus 4", "[1]"), ("psalm_verse", "4:2", "Filler verse & more."),
        ("versicle", "℣.", "Filler versicle"), ("rubric", None, "A whole red rubric."), ("text", None, "Plain text."),
    ]
    assert [(line.kind, line.text) for line in english.lines] == [("antiphon", "English filler.")]


def test_the_parser_reads_the_title_and_the_computed_day_data():
    parsed = parser.parse("<P ALIGN=CENTER><FONT >Some Feast ~ III. classis</FONT></P>" + ROW + "\n<!--DO-META\tEpi5\tSome Feast Duplex\t\twinner=Sancti/11-10.txt\tcommemoratio=\trank=3-->")
    assert parsed.title == "Some Feast ~ III. classis"
    assert parsed.meta["season_code"] == "Epi5" and parsed.meta["day"] == "Some Feast Duplex" and parsed.meta["winner"] == "Sancti/11-10.txt" and parsed.meta["rank"] == "3"


def test_a_row_without_a_latin_and_an_english_cell_is_refused_not_guessed():
    with pytest.raises(ValueError):
        parser.parse("<TR><TD>only one cell</TD></TR>")


def test_sections_start_at_each_heading_and_keep_the_latin_english_pairing():
    second = ROW.replace("Psalmi", "Hymnus").replace("Psalms", "Hymn")
    continued = "<TR><TD>x<br/>more Latin<br/></TD><TD>y<br/>more English<br/></TD></TR>"
    sections = service.build_sections(parser.parse(ROW + continued + second).rows)
    assert [(s.heading_latin, s.heading_english, len(s.rows)) for s in sections] == [("Psalmi", "Psalms", 2), ("Hymnus", "Hymn", 1)]
    assert sections[0].rows[1].latin[0].text == "x" and sections[0].rows[1].english[1].text == "more English"


def test_season_labels_come_from_the_engines_code_and_epiphany_sundays_resumed_in_november_are_not_called_epiphany():
    assert service.season_label("Quad2", date(2026, 3, 4)) == "Lent" and service.season_label("Pasc0", date(2026, 4, 8)) == "Eastertide"
    assert service.season_label("Adv4", date(2026, 12, 20)) == "Advent" and service.season_label("Pent11", date(2026, 8, 15)) == "Time after Pentecost"
    assert "Pentecost" in service.season_label("Epi5", date(2026, 11, 8)) and service.season_label("Epi2", date(2026, 1, 18)) == "Time after Epiphany"
    assert service.season_label("Zzz", date(2026, 1, 1)) is None


def test_the_engine_is_never_run_without_a_checkout_and_the_reason_is_plain():
    with pytest.raises(EngineUnavailable, match="not configured"):
        engine.run_engine(EngineConfig(None), date(2026, 11, 10), "prayCompletorium")
    with pytest.raises(EngineUnavailable, match="does not contain"):
        engine.run_engine(EngineConfig("C:/definitely/not/here"), date(2026, 11, 10), "prayCompletorium")
    with pytest.raises(EngineUnavailable, match="years"):
        engine.run_engine(EngineConfig(CHECKOUT or "x"), date(1850, 1, 1), "prayCompletorium")


def test_the_engine_is_asked_for_the_1960_rubrics_with_the_1960_calendar_not_the_new_calendar_variant():
    query = engine.query_for(date(2026, 11, 10), "prayCompletorium")
    assert "version=Rubrics 1960 - 1960" in query and "2020" not in query and "Newcal" not in query and "date=11-10-2026" in query


def test_all_eight_hours_are_listed_in_order_and_available():
    hours = service.hours_listing()
    assert [h["slug"] for h in hours] == ["matins", "lauds", "prime", "terce", "sext", "none", "vespers", "compline"]
    assert all(h["available"] for h in hours)


@needs_engine
def test_the_hour_commands_are_the_ones_the_upstream_engine_itself_lists():
    dialog = (Path(CHECKOUT) / "web" / "www" / "horas" / "horas.dialog").read_text(encoding="utf-8")
    listed = re.search(r"^\[horas\]\s*\n([^\n]+)", dialog, re.M).group(1).strip().split(",")
    assert listed == ["Matutinum", "Laudes", "Prima", "Tertia", "Sexta", "Nona", "Vesperae", "Completorium"]      # upstream's own names, in order
    assert [h["latin"] for h in service.HOURS] == listed and [h["command"] for h in service.HOURS] == ["pray" + name for name in listed]


# ---- The API ------------------------------------------------------------------------------------------------------
def test_the_api_needs_sign_in_and_says_plainly_when_the_engine_is_unavailable_or_the_hour_is_forthcoming(application):
    assert TestClient(application, headers={}).get("/api/divine-office/2026-11-10/compline").status_code == 401
    client = TestClient(application, headers=bearer("user_reader"))
    application.state.settings.divinum_officium_path = None
    unavailable = client.get("/api/divine-office/2026-11-10/compline")
    assert unavailable.status_code == 503 and "unavailable" in unavailable.json()["detail"] and "not configured" in unavailable.json()["detail"]
    for hour in ("matins", "lauds", "prime", "terce", "sext", "none", "vespers", "compline"):       # every hour reports the unavailable engine the same plain way
        assert client.get(f"/api/divine-office/2026-11-10/{hour}").status_code == 503, hour
    assert client.get("/api/divine-office/2026-11-10/midnight").status_code == 404
    assert client.get("/api/divine-office/not-a-date/compline").status_code == 422
    assert [h["slug"] for h in client.get("/api/divine-office/hours").json()] == [h["slug"] for h in service.hours_listing()]


@pytest.mark.parametrize("answer", ["", "Content-type: text/html\n\n<P>nothing</P>\n<!--DO-META\tEpi5\tA day\twinner=x\tcommemoratio=\trank=1-->", "<TR><TD>only one cell</TD></TR>\n<!--DO-META\tEpi5\tA day-->"])
def test_an_empty_or_malformed_engine_answer_is_an_error_never_an_empty_office(application, monkeypatch, answer):
    monkeypatch.setattr(service, "run_engine", lambda config, day, command: answer)
    service._cached.cache_clear()
    with pytest.raises(EngineUnavailable):
        service.office(CONFIG, date(2026, 11, 10), "vespers")
    application.state.settings.divinum_officium_path = "unused"
    response = TestClient(application, headers=bearer("user_reader")).get("/api/divine-office/2026-11-10/vespers")
    assert response.status_code == 503 and "unavailable" in response.json()["detail"]
    service._cached.cache_clear()


def test_a_failing_engine_process_is_reported_not_hidden(application, monkeypatch):
    def fail(config, day, command):
        raise EngineUnavailable("The Divinum Officium engine failed: boom")
    monkeypatch.setattr(service, "run_engine", fail)
    service._cached.cache_clear()
    application.state.settings.divinum_officium_path = "unused"
    response = TestClient(application, headers=bearer("user_reader")).get("/api/divine-office/2026-11-10/matins")
    assert response.status_code == 503 and "boom" in response.json()["detail"]
    service._cached.cache_clear()


# ---- Compline against the upstream engine, for contrasting dates ----------------------------------------------------------
DATES = {
    "ordinary weekday": date(2026, 11, 10),
    "Sunday": date(2026, 11, 8),
    "major feast (Assumption, I class)": date(2026, 8, 15),
    "Christmas": date(2026, 12, 25),
    "a Lenten weekday": date(2026, 3, 4),
    "Eastertide (Easter octave)": date(2026, 4, 8),
    "Eastertide, a feast (Ascension)": date(2026, 5, 14),
}
BASE_SEQUENCE = ["Incipit", "Lectio brevis", "Psalmi", "Hymnus", "Capitulum Responsorium Versus", "Canticum: Nunc dimittis", "Oratio", "Conclusio", "Antiphona finalis B.M.V."]


@needs_engine
@pytest.mark.parametrize("label", list(DATES))
def test_compline_has_the_full_sequence_in_both_languages_with_nothing_missing(label):
    office = service.office(CONFIG, DATES[label], "compline")
    headings = [s.heading_latin for s in office.sections]
    assert headings[0] == "Incipit" and headings[-1] == "Antiphona finalis B.M.V."                       # begins with the blessing, ends with the Marian antiphon
    assert set(headings) <= set(BASE_SEQUENCE) and [h for h in BASE_SEQUENCE if h in headings] == headings    # only known parts, in the upstream order
    assert {"Incipit", "Lectio brevis", "Psalmi", "Canticum: Nunc dimittis", "Oratio", "Conclusio", "Antiphona finalis B.M.V."} <= set(headings)
    for section in office.sections:
        assert section.heading_english and any(row.latin for row in section.rows) and any(row.english for row in section.rows), (label, section.heading_latin)
    psalms = [line for s in office.sections for r in s.rows for line in r.latin if line.kind == "psalm_heading"]
    assert len(psalms) == 4 and psalms[-1].label == "Canticum Simeonis"                                      # three psalms and the Nunc dimittis
    verses = {kind: sum(1 for s in office.sections for r in s.rows for line in r.latin if line.kind == kind) for kind in ("psalm_verse", "antiphon", "versicle", "response")}
    assert verses["psalm_verse"] > 20 and verses["antiphon"] >= 2 and verses["versicle"] >= 4 and verses["response"] >= 4
    assert office.source.version == "Rubrics 1960 - 1960" and office.hour == "compline"


@needs_engine
@pytest.mark.parametrize("label", list(DATES))
def test_every_word_in_the_response_is_the_engines_and_nothing_else_was_added(label):
    raw = engine.run_engine(CONFIG, DATES[label], "prayCompletorium")
    office = service.office(CONFIG, DATES[label], "compline")
    for index, language in ((0, "latin"), (1, "english")):
        cells = [parser.CELL.findall(row)[index] for row in parser.ROW.findall(raw)]
        expected = " ".join(parser.plain(parser.NAV.sub("", cell, count=1)) for cell in cells)
        got = " ".join(
            " ".join(part for part in (heading, note, *[f"{line.label or ''} {line.text}" for row in section.rows for line in getattr(row, language)]) if part)
            for section in office.sections for heading, note in [(getattr(section, f"heading_{language}"), getattr(section, f"note_{language}"))]
        )
        squash = lambda value: re.sub(r"\s+", "", value)  # noqa: E731
        assert squash(got) == squash(expected), (label, language)


@needs_engine
def test_the_1960_universal_calendar_gives_these_days_and_ranks():
    avellino = service.office(CONFIG, date(2026, 11, 10), "compline")
    assert "Andreæ Avellini" in avellino.liturgical_day and avellino.rank == "III. classis"           # 10 Nov: St Andrew Avellino, a III class feast in the 1960 calendar
    christmas = service.office(CONFIG, date(2026, 12, 25), "compline")
    assert "Nativitate" in christmas.liturgical_day and christmas.rank == "I. classis" and christmas.season == "Christmastide"


@needs_engine
def test_contrasting_dates_give_contrasting_offices_from_the_engine():
    texts = {label: service.office(CONFIG, day, "compline") for label, day in DATES.items()}
    sunday = [x.label for s in texts["Sunday"].sections for r in s.rows for x in r.latin if x.kind == "psalm_heading"]
    weekday = [x.label for s in texts["ordinary weekday"].sections for r in s.rows for x in r.latin if x.kind == "psalm_heading"]
    lent = [x.label for s in texts["a Lenten weekday"].sections for r in s.rows for x in r.latin if x.kind == "psalm_heading"]
    assert sunday[:3] == ["Psalmus 4", "Psalmus 90", "Psalmus 133"] and weekday[:3] != sunday[:3] and lent[:3] != weekday[:3]
    assert "Quadragesima" in texts["a Lenten weekday"].liturgical_day and texts["a Lenten weekday"].season == "Lent"
    assert "Assumptione" in texts["major feast (Assumption, I class)"].liturgical_day
    octave = texts["Eastertide (Easter octave)"]
    assert octave.season == "Eastertide" and "Paschæ" in octave.liturgical_day
    assert "Hymnus" not in [s.heading_latin for s in octave.sections]                                          # the engine omits the hymn in the Easter octave: reported as it is, not "fixed"


@needs_engine
def test_the_api_returns_the_structure_and_can_narrow_to_one_language(application):
    application.state.settings.divinum_officium_path = CHECKOUT
    application.state.settings.divinum_officium_perl5lib = PERL5LIB
    client = TestClient(application, headers=bearer("user_reader"))
    both = client.get("/api/divine-office/2026-11-10/compline").json()
    assert both["hour"] == "compline" and both["source"]["name"] == "Divinum Officium" and both["source"]["version"] == "Rubrics 1960 - 1960"
    assert re.fullmatch(r"[0-9a-f]{40}", both["source"]["commit"] or "") and both["source"]["code_license"].startswith("MIT")
    latin = client.get("/api/divine-office/2026-11-10/compline?language=latin").json()
    assert all(not row["english"] for s in latin["sections"] for row in s["rows"]) and latin["sections"][0]["heading_english"] is None
    english = client.get("/api/divine-office/2026-11-10/compline?language=english").json()
    assert all(not row["latin"] for s in english["sections"] for row in s["rows"]) and english["sections"][0]["heading_latin"] is None
    assert client.get("/api/divine-office/2026-11-10/compline?language=klingon").status_code == 422


# ---- All eight hours, for contrasting dates, against the upstream engine -----------------------------------------------
ALL_DATES = {
    "ordinary weekday": date(2026, 11, 10), "Sunday": date(2026, 11, 8), "major feast (Assumption)": date(2026, 8, 15), "Christmas": date(2026, 12, 25),
    "Lenten weekday with commemorations": date(2026, 3, 4), "Lenten Sunday": date(2026, 3, 8), "Easter octave": date(2026, 4, 8), "Vigil of the Ascension": date(2026, 5, 13), "Ascension": date(2026, 5, 14),
}
TRIDUUM = {"Good Friday": date(2026, 4, 3), "Holy Saturday": date(2026, 4, 4)}
SLUGS = [h["slug"] for h in service.HOURS]
# The parts each hour may contain, in the order upstream gives them, and those every ordinary Office has.
CANON = {
    "matins": ["Incipit", "Invitatorium", "Hymnus", "Psalmi cum lectionibus", "Oratio", "Conclusio"],
    "lauds": ["Incipit", "Psalmi", "Capitulum Hymnus Versus", "Versus (In loco Capituli)", "Canticum: Benedictus", "Preces Feriales", "Oratio", "Conclusio"],
    "prime": ["Incipit", "Hymnus", "Psalmi", "Capitulum Responsorium Versus", "Versus (In loco Capituli)", "Oratio", "Martyrologium", "De Officio Capituli", "Lectio brevis", "Conclusio"],
    "terce": ["Incipit", "Hymnus", "Psalmi", "Capitulum Responsorium Versus", "Versus (In loco Capituli)", "Oratio", "Conclusio"],
    "sext": ["Incipit", "Hymnus", "Psalmi", "Capitulum Responsorium Versus", "Versus (In loco Capituli)", "Oratio", "Conclusio"],
    "none": ["Incipit", "Hymnus", "Psalmi", "Capitulum Responsorium Versus", "Versus (In loco Capituli)", "Oratio", "Conclusio"],
    "vespers": ["Incipit", "Psalmi", "Capitulum Hymnus Versus", "Versus (In loco Capituli)", "Canticum: Magnificat", "Preces Feriales", "Oratio", "Conclusio"],
    "compline": BASE_SEQUENCE,
}
REQUIRED = {
    "matins": {"Incipit", "Invitatorium", "Psalmi cum lectionibus", "Oratio", "Conclusio"}, "lauds": {"Incipit", "Psalmi", "Canticum: Benedictus", "Oratio", "Conclusio"},
    "prime": {"Incipit", "Psalmi", "Oratio", "Martyrologium", "De Officio Capituli", "Lectio brevis", "Conclusio"}, "terce": {"Incipit", "Psalmi", "Oratio", "Conclusio"},
    "sext": {"Incipit", "Psalmi", "Oratio", "Conclusio"}, "none": {"Incipit", "Psalmi", "Oratio", "Conclusio"},
    "vespers": {"Incipit", "Psalmi", "Canticum: Magnificat", "Oratio", "Conclusio"}, "compline": {"Incipit", "Lectio brevis", "Psalmi", "Canticum: Nunc dimittis", "Oratio", "Conclusio", "Antiphona finalis B.M.V."},
}
CASES = [(hour, label) for hour in SLUGS for label in ALL_DATES]


def lines_of(office, language="latin"):
    return [line for section in office.sections for row in section.rows for line in getattr(row, language)]


@needs_engine
@pytest.mark.parametrize(("hour", "label"), CASES)
def test_every_hour_has_its_parts_in_the_upstream_order_with_both_languages(hour, label):
    office = service.office(CONFIG, ALL_DATES[label], hour)
    headings = [s.heading_latin for s in office.sections]
    assert None not in headings and set(headings) <= set(CANON[hour]), (hour, label, headings)                   # only known parts of this hour
    assert [h for h in CANON[hour] if h in headings] == headings, (hour, label, headings)                       # in upstream's order, none repeated
    assert REQUIRED[hour] <= set(headings), (hour, label, REQUIRED[hour] - set(headings))                        # nothing essential missing
    if hour in {"lauds", "vespers"}:
        assert {"Capitulum Hymnus Versus", "Versus (In loco Capituli)"} & set(headings)                           # a chapter-and-hymn, or the Easter-octave verse in its place
    for section in office.sections:
        assert section.heading_english and any(r.latin for r in section.rows) and any(r.english for r in section.rows), (hour, label, section.heading_latin)
    assert office.hour == hour and office.liturgical_day and office.source.version == "Rubrics 1960 - 1960"


@needs_engine
@pytest.mark.parametrize(("hour", "label"), CASES)
def test_psalmody_and_responses_are_present_where_the_hour_has_them(hour, label):
    office = service.office(CONFIG, ALL_DATES[label], hour)
    kinds = {kind: sum(1 for line in lines_of(office) if line.kind == kind) for kind in ("psalm_heading", "psalm_verse", "antiphon", "versicle", "response")}
    assert kinds["psalm_verse"] >= 10 and kinds["psalm_heading"] >= 1 and kinds["antiphon"] >= 1, (hour, label, kinds)
    assert kinds["versicle"] >= 2 and kinds["response"] >= 2, (hour, label, kinds)
    english = {kind: sum(1 for line in lines_of(office, "english") if line.kind == kind) for kind in kinds}
    assert english["psalm_verse"] == kinds["psalm_verse"] and english["antiphon"] == kinds["antiphon"], (hour, label)    # the English carries the same psalms and antiphons


@needs_engine
@pytest.mark.parametrize(("hour", "label"), [(h, label) for h in SLUGS for label in {**ALL_DATES, **TRIDUUM}])
def test_every_word_of_every_hour_is_the_engines_and_nothing_else_was_added_or_dropped(hour, label):
    day = {**ALL_DATES, **TRIDUUM}[label]
    command = next(h["command"] for h in service.HOURS if h["slug"] == hour)
    raw = engine.run_engine(CONFIG, day, command)
    office = service.office(CONFIG, day, hour)
    squash = lambda value: re.sub(r"\s+", "", value)  # noqa: E731
    for index, language in ((0, "latin"), (1, "english")):
        cells = [parser.CELL.findall(row)[index] for row in parser.ROW.findall(raw)]
        expected = " ".join(parser.plain(parser.NAV.sub("", cell, count=1)) for cell in cells)
        got = " ".join(
            " ".join(part for part in (getattr(section, f"heading_{language}"), getattr(section, f"note_{language}"), *[f"{line.label or ''} {line.text}" for row in section.rows for line in getattr(row, language)]) if part)
            for section in office.sections
        )
        assert squash(got) == squash(expected), (hour, label, language)


@needs_engine
@pytest.mark.parametrize("label", list(TRIDUUM))
def test_the_triduum_is_carried_whole_even_though_it_has_no_ordinary_headings(label):
    for hour in SLUGS:
        office = service.office(CONFIG, TRIDUUM[label], hour)
        assert office.sections and all(any(r.latin for r in s.rows) and any(r.english for r in s.rows) for s in office.sections), (hour, label)


@needs_engine
def test_latin_and_english_rows_are_parallel_except_where_the_engines_own_texts_are_not():
    unaligned = {}
    for hour in SLUGS:
        for label, day in ALL_DATES.items():
            office = service.office(CONFIG, day, hour)
            for section in office.sections:
                for row in section.rows:
                    assert row.aligned == (len(row.latin) == len(row.english))
                    if not row.aligned:
                        unaligned.setdefault((hour, label), []).append(section.heading_latin)
    flagged = {(hour, heading) for (hour, _label), headings in unaligned.items() for heading in headings}
    assert flagged <= {("matins", "Psalmi cum lectionibus"), ("prime", "Martyrologium")}, unaligned              # known: the Martyrology and one Matins reading split their lines differently in the two languages
    assert sum(len(v) for v in unaligned.values()) <= 6


@needs_engine
def test_matins_on_a_feast_of_the_first_class_has_three_nocturns_nine_lessons_and_the_te_deum():
    for label in ("Christmas", "major feast (Assumption)"):
        office = service.office(CONFIG, ALL_DATES[label], "matins")
        marks = [(m.kind, m.latin, m.english) for s in office.sections for r in s.rows for m in r.marks]
        assert [m[1] for m in marks if m[0] == "nocturn"] == ["Nocturnus I", "Nocturnus II", "Nocturnus III"], label
        assert all(m[2] for m in marks)                                                                           # each mark has its English counterpart
        assert any(m[0] == "te_deum" for m in marks)
        assert sum(1 for line in lines_of(office) if re.fullmatch(r"Lectio \d", line.text)) == 9
        assert sum(1 for line in lines_of(office) if line.kind == "psalm_heading") == 9
        assert [s.heading_latin for s in office.sections].count("Psalmi cum lectionibus") == 1                  # one section, the nocturns inside it, none repeated


@needs_engine
def test_matins_on_an_ordinary_day_has_one_nocturn_and_no_te_deum_in_lent():
    sunday = service.office(CONFIG, ALL_DATES["Sunday"], "matins")
    lent = service.office(CONFIG, ALL_DATES["Lenten weekday with commemorations"], "matins")
    for office in (sunday, lent):
        assert [m.latin for s in office.sections for r in s.rows for m in r.marks if m.kind == "nocturn"] == ["Ad Nocturnum"]
        assert sum(1 for line in lines_of(office) if re.fullmatch(r"Lectio \d", line.text)) == 3
    assert not any(m.kind == "te_deum" for s in lent.sections for r in s.rows for m in r.marks)


@needs_engine
def test_commemorations_are_kept_and_marked_in_lauds():
    office = service.office(CONFIG, ALL_DATES["Lenten weekday with commemorations"], "lauds")
    marks = [m for s in office.sections for r in s.rows for m in r.marks if m.kind == "commemoration"]
    assert [m.latin for m in marks] == ["Commemoratio S. Casimiri Confessoris", "Commemoratio S. Lucii I Papæ et Martyris"]
    assert all(m.english and "Commemoration" in m.english for m in marks)
    assert "Preces Feriales" in [s.heading_latin for s in office.sections]                                         # Lenten ferial preces are present


@needs_engine
def test_the_ordinary_weekday_and_the_sunday_differ_as_the_engine_says_for_every_hour():
    for hour in SLUGS:
        weekday, sunday = service.office(CONFIG, ALL_DATES["ordinary weekday"], hour), service.office(CONFIG, ALL_DATES["Sunday"], hour)
        assert [x.text for x in lines_of(weekday)] != [x.text for x in lines_of(sunday)], hour


@needs_engine
def test_compline_is_unchanged_by_the_other_hours(application):
    before = service.office(CONFIG, date(2026, 11, 10), "compline")
    for hour in SLUGS[:-1]:
        service.office(CONFIG, date(2026, 11, 10), hour)
    after = service.office(CONFIG, date(2026, 11, 10), "compline")
    assert before == after and [s.heading_latin for s in after.sections] == BASE_SEQUENCE
    assert after.liturgical_day.startswith("S. Andreæ Avellini") and after.rank == "III. classis"


@needs_engine
def test_the_api_serves_every_hour_and_narrowing_keeps_the_other_language_out(application):
    application.state.settings.divinum_officium_path = CHECKOUT
    application.state.settings.divinum_officium_perl = PERL
    application.state.settings.divinum_officium_perl5lib = PERL5LIB
    client = TestClient(application, headers=bearer("user_reader"))
    for hour in SLUGS:
        both = client.get(f"/api/divine-office/2026-12-25/{hour}")
        assert both.status_code == 200 and both.json()["hour"] == hour and both.json()["source"]["version"] == "Rubrics 1960 - 1960"
    latin = client.get("/api/divine-office/2026-12-25/matins?language=latin").json()
    english = client.get("/api/divine-office/2026-12-25/matins?language=english").json()
    assert all(not row["english"] and all(m["english"] is None for m in row["marks"]) for s in latin["sections"] for row in s["rows"])
    assert all(not row["latin"] and all(m["latin"] == "" for m in row["marks"]) for s in english["sections"] for row in s["rows"])
    assert "Nocturnus" not in str(english) and "Nocturn" in str(english)
