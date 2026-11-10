# ruff: noqa: E501
"""Saving Divine Office prayers: which units are offered (and which are not), the server-verified snapshot, and per-user isolation."""

from datetime import date

import pytest
from clerk_tokens import bearer
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select
from test_devotions import add_devotion
from test_divine_office import CHECKOUT, PERL, PERL5LIB, needs_engine

from app.divine_office import service, units
from app.divine_office.engine import EngineConfig
from app.divine_office.parser import Cell, Line
from app.models import SavedOfficeUnit

CONFIG = EngineConfig(CHECKOUT, PERL, PERL5LIB)
SLUGS = [h["slug"] for h in service.HOURS]
DAY = date(2026, 11, 10)


def L(kind, text, label=None):
    return Line(kind, text, label)


def cells(latin, english):
    return Cell(lines=latin), Cell(lines=english)


def parallel(lines):
    """The same shape in both languages, with filler text."""
    return [L(k, f"Latin {t}", lab) for k, t, lab in lines], [L(k, f"English {t}", lab.replace("Psalmus", "Psalm") if lab else lab) for k, t, lab in lines]


# ---- Which units are offered, on synthetic rows ---------------------------------------------------------------------
def test_a_psalm_is_a_heading_with_its_numbered_verses_and_stops_before_the_doxology():
    lat, eng = parallel([("antiphon", "ant", "Ant."), ("psalm_heading", "[1]", "Psalmus 4"), ("psalm_verse", "v1", "4:2"), ("psalm_verse", "v2", "4:3"), ("versicle", "gloria", "℣."), ("response", "sicut", "℟."), ("antiphon", "ant again", "Ant.")])
    found = units.row_units(*cells(lat, eng), "Psalmi", "Psalms", DAY, "compline", False)
    assert [(u.kind, u.title_latin, u.title_english, u.start, u.end) for u in found] == [("antiphon", "Antiphona ad Psalmus 4", "Antiphon to Psalm 4", 0, 1), ("psalm", "Psalmus 4", "Psalm 4", 1, 4)]
    assert found[0].date_specific and not found[1].date_specific                                   # the antiphon is the day's; the psalm is fixed
    assert found[0].id.startswith("antiphon:2026-11-10:compline:") and found[1].id.startswith("psalm:")


def test_a_canticle_includes_its_scripture_reference_and_is_titled_from_the_section_not_the_antiphon():
    lat, eng = parallel([("antiphon", "ant", "Ant."), ("psalm_heading", "", "Canticum Simeonis"), ("rubric", "Luc. 2:29-32", None), ("psalm_verse", "v1", "2:29"), ("psalm_verse", "v2", "2:30")])
    found = units.row_units(*cells(lat, eng), "Canticum: Nunc dimittis", "Canticle: Nunc dimittis", DAY, "compline", True)
    canticle = next(u for u in found if u.kind == "canticle")
    assert (canticle.title_latin, canticle.title_english, canticle.start, canticle.end) == ("Nunc dimittis", "Nunc dimittis", 1, 5)
    assert next(u for u in found if u.kind == "antiphon").title_english == "Antiphon to Nunc dimittis"      # the variable antiphon is a separate, dated unit


def test_the_same_canticle_has_the_same_id_on_any_day_but_its_antiphon_does_not():
    lat, eng = parallel([("antiphon", "ant", "Ant."), ("psalm_heading", "", "Canticum B. Mariæ Virginis"), ("psalm_verse", "v1", "1:46")])
    monday = {u.kind: u.id for u in units.row_units(*cells(lat, eng), "Canticum: Magnificat", "Canticle: Magnificat", date(2026, 11, 9), "vespers", True)}
    tuesday = {u.kind: u.id for u in units.row_units(*cells(lat, eng), "Canticum: Magnificat", "Canticle: Magnificat", date(2026, 11, 10), "vespers", True)}
    assert monday["canticle"] == tuesday["canticle"] and monday["antiphon"] != tuesday["antiphon"]


def test_a_hymn_follows_the_hymnus_rubric_through_plain_lines_up_to_the_versicle_or_is_a_whole_hymnus_section():
    lat, eng = parallel([("rubric", "Hymnus", None)] + [("text", f"line {n}", None) for n in range(5)] + [("versicle", "v", "℣.")])
    eng[0] = L("rubric", "Hymn")
    lat[0] = L("rubric", "Hymnus")
    found = units.row_units(*cells(lat, eng), "Capitulum Hymnus Versus", "Chapter Hymn Verse", DAY, "vespers", True)
    assert [(u.kind, u.start, u.end) for u in found] == [("hymn", 1, 6)] and found[0].title_latin == "Hymnus: Latin line 0"
    lat2, eng2 = parallel([("text", f"stanza {n}", None) for n in range(4)])
    whole = units.row_units(*cells(lat2, eng2), "Hymnus", "Hymn", DAY, "terce", True)
    assert [(u.kind, u.start, u.end) for u in whole] == [("hymn", 0, 4)]
    assert units.row_units(*cells(lat2, eng2), "Hymnus", "Hymn", DAY, "terce", False) == []                    # a Hymnus section spread over several rows is not offered


@pytest.mark.parametrize(("name", "lines", "section"), [
    ("a chapter", [("rubric", "Ier 14:9", None), ("text", "Tu autem", None), ("response", "Deo gratias", "℟.")], "Capitulum Responsorium Versus"),
    ("a lesson", [("text", "Lectio 1", None), ("rubric", "Dan 1:1-4", None), ("text", "In anno", None)], "Psalmi cum lectionibus"),
    ("a collect", [("versicle", "Domine exaudi", "℣."), ("response", "Et clamor", "℟."), ("text", "Orémus.", None), ("text", "Deus qui", None), ("response", "Amen.", "℟.")], "Oratio"),
    ("a responsory", [("response", "Responsorium", "℟."), ("versicle", "In manus", "℣.")], "Capitulum Responsorium Versus"),
    ("a short hymn-like run", [("rubric", "Hymnus", None), ("text", "one", None), ("text", "two", None)], "Capitulum Hymnus Versus"),
    ("an antiphon not before a psalm", [("antiphon", "Salva nos", "Ant."), ("text", "x", None)], "Canticum: Nunc dimittis"),
    ("a psalm heading with no verses", [("psalm_heading", "[1]", "Psalmus 4"), ("versicle", "gloria", "℣.")], "Psalmi"),
])
def test_chapters_lessons_collects_responsories_and_unclear_boundaries_are_not_offered(name, lines, section):
    lat, eng = parallel(lines)
    if lines[0][1] == "Hymnus":
        lat[0], eng[0] = L("rubric", "Hymnus"), L("rubric", "Hymn")
    assert units.row_units(*cells(lat, eng), section, section, DAY, "lauds", True) == [], name


def test_a_row_whose_languages_do_not_line_up_offers_nothing():
    lat, eng = parallel([("psalm_heading", "[1]", "Psalmus 4"), ("psalm_verse", "v1", "4:2"), ("psalm_verse", "v2", "4:3")])
    assert units.row_units(*cells(lat, eng[:-1]), "Psalmi", "Psalms", DAY, "prime", False) == []                # one line fewer in English
    eng[2] = L("text", "English v2")                                                                          # same count, different kind
    assert units.row_units(*cells(lat, eng), "Psalmi", "Psalms", DAY, "prime", False) == []


def test_an_id_that_would_occur_twice_in_one_office_is_withdrawn():
    lat, eng = parallel([("rubric", "Hymnus", None)] + [("text", f"line {n}", None) for n in range(5)])
    lat[0], eng[0] = L("rubric", "Hymnus"), L("rubric", "Hymn")
    rows = [cells(lat, eng), cells(lat, eng)]
    sections = service.build_sections(rows, DAY, "vespers")
    assert all(not row.units for section in sections for row in section.rows)                                 # identical text twice: ambiguous, so no Save button for either
    assert [len(r.units) for s in service.build_sections(rows[:1], DAY, "vespers") for r in s.rows] == [1]


def test_the_id_format_is_validated_and_reproducible():
    assert units.ID_PATTERN.match("psalm:0123456789abcdef") and units.ID_PATTERN.match("antiphon:2026-11-10:compline:0123456789abcdef")
    for bad in ("psalm:xyz", "psalm:0123456789abcdef; drop", "lesson:0123456789abcdef", "antiphon:0123456789abcdef", "<b>x</b>", ""):
        assert not units.ID_PATTERN.match(bad)
    lines = [L("psalm_heading", "[1]", "Psalmus 4")]
    assert units.unit_id("psalm", lines, DAY, "prime") == units.unit_id("psalm", lines, date(2027, 1, 1), "vespers")


# ---- Against the upstream engine -------------------------------------------------------------------------------------------
@needs_engine
@pytest.mark.parametrize("hour", SLUGS)
def test_every_hour_offers_unique_reproducible_units_and_never_a_chapter_lesson_or_collect(hour):
    for day in (date(2026, 11, 10), date(2026, 12, 25), date(2026, 3, 4), date(2026, 4, 8)):
        office = service.office(CONFIG, day, hour)
        found = [(row, u) for s in office.sections for row in s.rows for u in row.units]
        ids = [u.id for _, u in found]
        assert len(ids) == len(set(ids)), (hour, day)
        assert any(u.kind == "psalm" for _, u in found), (hour, day)
        for row, u in found:
            assert u.kind in units.KINDS and units.ID_PATTERN.match(u.id) and 0 <= u.start < u.end <= len(row.latin) == len(row.english)
            assert [x.kind for x in row.latin[u.start:u.end]] == [x.kind for x in row.english[u.start:u.end]]
            kinds = {x.kind for x in row.latin[u.start:u.end]}
            assert not kinds & {"versicle", "response", "benediction"}, (hour, day, u.title_english)           # no responsory, collect or lesson tail
            assert not any(x.text in {"Orémus.", "Deo grátias."} for x in row.latin[u.start:u.end])
        again = service.build_sections(__import__("app.divine_office.parser", fromlist=["parse"]).parse(__import__("app.divine_office.engine", fromlist=["run_engine"]).run_engine(CONFIG, day, next(h["command"] for h in service.HOURS if h["slug"] == hour))).rows, day, hour)
        assert [u.id for s in again for r in s.rows for u in r.units] == ids                                     # reproducible from the engine's output


@needs_engine
def test_fixed_prayers_keep_their_id_across_dates_and_antiphons_do_not():
    sunday_a, sunday_b = service.office(CONFIG, date(2026, 11, 8), "compline"), service.office(CONFIG, date(2026, 8, 15), "compline")
    flat = lambda o, kind: {u.title_english: u.id for s in o.sections for r in s.rows for u in r.units if u.kind == kind}  # noqa: E731
    assert flat(sunday_a, "psalm")["Psalm 4"] == flat(sunday_b, "psalm")["Psalm 4"]
    assert flat(sunday_a, "canticle")["Nunc dimittis"] == flat(sunday_b, "canticle")["Nunc dimittis"]
    ants_a, ants_b = flat(sunday_a, "antiphon"), flat(sunday_b, "antiphon")
    assert set(ants_a.values()).isdisjoint(ants_b.values())                                                        # an antiphon id always names its date and hour


# ---- The API --------------------------------------------------------------------------------------------------------------
@pytest.fixture
def engine_on(application):
    application.state.settings.divinum_officium_path = CHECKOUT
    application.state.settings.divinum_officium_perl = PERL
    application.state.settings.divinum_officium_perl5lib = PERL5LIB


def user(application, name):
    return TestClient(application, headers=bearer(name))


def unit_of(client, day, hour, kind, title=None):
    office = client.get(f"/api/divine-office/{day}/{hour}").json()
    return next(u for s in office["sections"] for r in s["rows"] for u in r["units"] if u["kind"] == kind and (title is None or u["title_english"] == title))


def save(client, day, hour, unit_id):
    return client.post("/api/divine-office/saved", json={"date": day, "hour": hour, "unit_id": unit_id})


@needs_engine
def test_the_migration_created_the_table_and_the_office_offers_units_through_the_api(application, engine_on):
    assert "saved_office_units" in inspect(application.state.engine).get_table_names()
    client = user(application, "user_a")
    row = next(r for s in client.get("/api/divine-office/2026-11-10/compline").json()["sections"] for r in s["rows"] if r["units"])
    assert {"id", "kind", "title_latin", "title_english", "start", "end", "date_specific"} <= set(row["units"][0])


@needs_engine
def test_saving_and_unsaving_a_psalm_with_its_exact_snapshot_and_provenance(application, engine_on):
    client = user(application, "user_a")
    psalm = unit_of(client, "2026-11-10", "compline", "psalm", "Psalm 11")
    created = save(client, "2026-11-10", "compline", psalm["id"])
    assert created.status_code == 201 and created.json()["saved"] is True
    item = created.json()["item"]
    assert (item["kind"], item["title_english"], item["source_hour"], item["source_hour_name"], item["source_date"], item["date_specific"]) == ("psalm", "Psalm 11", "compline", "Compline", "2026-11-10", False)
    detail = client.get(f"/api/divine-office/saved/{item['id']}").json()
    office = client.get("/api/divine-office/2026-11-10/compline").json()
    row = next(r for s in office["sections"] for r in s["rows"] if any(u["id"] == psalm["id"] for u in r["units"]))
    assert detail["latin"] == row["latin"][psalm["start"]:psalm["end"]] and detail["english"] == row["english"][psalm["start"]:psalm["end"]]    # original wording, both languages, in order
    assert detail["latin"][0]["label"] == "Psalmus 11" and detail["english"][0]["label"] == "Psalm 11" and len(detail["latin"]) > 5
    assert detail["source"]["name"] == "Divinum Officium" and detail["source"]["version"] == "Rubrics 1960 - 1960" and len(detail["source"]["commit"]) == 40
    assert "rights" in detail["source"]["texts"]
    assert client.get("/api/divine-office/saved").json()[0]["id"] == item["id"]
    assert client.delete(f"/api/divine-office/saved/{item['id']}").json() == {"saved": False}
    assert client.get("/api/divine-office/saved").json() == [] and client.get(f"/api/divine-office/saved/{item['id']}").status_code == 404


@needs_engine
def test_saving_the_same_selection_again_or_from_another_day_creates_no_duplicate(application, engine_on):
    client = user(application, "user_a")
    first = unit_of(client, "2026-11-08", "compline", "psalm", "Psalm 4")
    again = unit_of(client, "2026-08-15", "compline", "psalm", "Psalm 4")
    assert first["id"] == again["id"]
    one = save(client, "2026-11-08", "compline", first["id"])
    two = save(client, "2026-11-08", "compline", first["id"])
    three = save(client, "2026-08-15", "compline", again["id"])
    assert (one.status_code, two.status_code, three.status_code) == (201, 200, 200)
    assert two.json()["item"]["id"] == one.json()["item"]["id"] == three.json()["item"]["id"]
    assert three.json()["item"]["source_date"] == "2026-11-08"                                                      # it keeps the first save's provenance
    with application.state.session_factory() as db:
        assert len(list(db.scalars(select(SavedOfficeUnit)))) == 1


@needs_engine
def test_a_hymn_and_a_canticle_can_be_saved_and_the_magnificat_is_distinct_from_its_antiphon(application, engine_on):
    client = user(application, "user_a")
    hymn = unit_of(client, "2026-11-10", "vespers", "hymn")
    magnificat = unit_of(client, "2026-11-10", "vespers", "canticle", "Magnificat")
    antiphon = next(u for s in client.get("/api/divine-office/2026-11-10/vespers").json()["sections"] if s["heading_latin"] == "Canticum: Magnificat" for r in s["rows"] for u in r["units"] if u["kind"] == "antiphon")
    saved = {k: save(client, "2026-11-10", "vespers", u["id"]).json()["item"] for k, u in (("hymn", hymn), ("canticle", magnificat), ("antiphon", antiphon))}
    canticle = client.get(f"/api/divine-office/saved/{saved['canticle']['id']}").json()
    assert {x["kind"] for x in canticle["latin"]} <= {"psalm_heading", "rubric", "psalm_verse"} and canticle["latin"][0]["label"].startswith("Canticum")      # the fixed canticle holds no antiphon
    assert saved["canticle"]["date_specific"] is False and saved["antiphon"]["date_specific"] is True
    assert saved["antiphon"]["unit_key"].startswith("antiphon:2026-11-10:vespers:") and saved["canticle"]["unit_key"].startswith("canticle:")
    hymn_detail = client.get(f"/api/divine-office/saved/{saved['hymn']['id']}").json()
    assert all(x["kind"] == "text" for x in hymn_detail["latin"]) and hymn_detail["latin"][-1]["text"] == "Amen." and len(hymn_detail["latin"]) == len(hymn_detail["english"]) >= 5
    ant = client.get(f"/api/divine-office/saved/{saved['antiphon']['id']}").json()
    assert [x["kind"] for x in ant["latin"]] == ["antiphon"] and ant["source_date"] == "2026-11-10" and ant["source_hour"] == "vespers"


@needs_engine
def test_a_date_specific_antiphon_is_a_different_selection_on_a_different_day(application, engine_on):
    client = user(application, "user_a")
    ids = []
    for day in ("2026-11-10", "2026-11-11"):
        antiphon = next(u for s in client.get(f"/api/divine-office/{day}/compline").json()["sections"] for r in s["rows"] for u in r["units"] if u["kind"] == "antiphon")
        ids.append(save(client, day, "compline", antiphon["id"]).json()["item"])
    assert ids[0]["id"] != ids[1]["id"] and {i["source_date"] for i in ids} == {"2026-11-10", "2026-11-11"}


@needs_engine
def test_saved_prayers_are_private_to_their_user(application, engine_on):
    alice, bob = user(application, "user_alice"), user(application, "user_bob")
    psalm = unit_of(alice, "2026-11-10", "compline", "psalm", "Psalm 11")
    mine = save(alice, "2026-11-10", "compline", psalm["id"]).json()["item"]
    assert bob.get("/api/divine-office/saved").json() == []
    assert bob.get(f"/api/divine-office/saved/{mine['id']}").status_code == 404
    assert bob.delete(f"/api/divine-office/saved/{mine['id']}").status_code == 404                                  # cannot remove someone else's
    assert alice.get(f"/api/divine-office/saved/{mine['id']}").status_code == 200
    theirs = save(bob, "2026-11-10", "compline", psalm["id"])
    assert theirs.status_code == 201 and theirs.json()["item"]["id"] != mine["id"]                                  # the same prayer, saved separately by each user
    assert len(alice.get("/api/divine-office/saved").json()) == 1 and len(bob.get("/api/divine-office/saved").json()) == 1


@needs_engine
def test_the_client_cannot_supply_prayer_text_or_an_invalid_reference(application, engine_on):
    client = user(application, "user_a")
    psalm = unit_of(client, "2026-11-10", "compline", "psalm", "Psalm 11")
    base = {"date": "2026-11-10", "hour": "compline", "unit_id": psalm["id"]}
    assert client.post("/api/divine-office/saved", json={**base, "latin": "<script>alert(1)</script>"}).status_code == 422       # no client text is accepted
    assert client.post("/api/divine-office/saved", json={**base, "title": "My own text"}).status_code == 422
    assert client.post("/api/divine-office/saved", json={**base, "unit_id": "psalm:xyz"}).status_code == 422
    assert client.post("/api/divine-office/saved", json={**base, "hour": "midnight"}).status_code == 422
    assert client.post("/api/divine-office/saved", json={**base, "date": "2026-13-45"}).status_code == 422
    assert client.post("/api/divine-office/saved", json={"date": "2026-11-10", "hour": "compline"}).status_code == 422
    assert save(client, "2026-11-10", "compline", "psalm:0123456789abcdef").status_code == 404                                   # well formed, but not a unit of that Office
    assert save(client, "2026-11-11", "compline", psalm["id"]).status_code == 404                                               # Psalm 11 is not in the Compline of that day
    assert client.get("/api/divine-office/saved/not-a-uuid").status_code == 422
    assert client.get("/api/divine-office/saved").json() == []


def test_saving_needs_sign_in_and_reports_an_unavailable_engine(application):
    anonymous = TestClient(application, headers={})
    assert anonymous.get("/api/divine-office/saved").status_code == 401
    assert anonymous.post("/api/divine-office/saved", json={"date": "2026-11-10", "hour": "compline", "unit_id": "psalm:0123456789abcdef"}).status_code == 401
    application.state.settings.divinum_officium_path = None
    response = save(user(application, "user_a"), "2026-11-10", "compline", "psalm:0123456789abcdef")
    assert response.status_code == 503 and "unavailable" in response.json()["detail"]


@needs_engine
def test_existing_devotion_bookmarks_are_untouched_by_saved_office_prayers(application, engine_on):
    add_devotion(application, "one", texts=[("main", "en", "Filler wording")])
    client = user(application, "user_a")
    assert client.put("/api/devotions/one/bookmark").json() == {"bookmarked": True}
    save(client, "2026-11-10", "compline", unit_of(client, "2026-11-10", "compline", "psalm", "Psalm 11")["id"])
    assert client.get("/api/devotions/one").json()["bookmarked"] is True and [d["slug"] for d in client.get("/api/devotions").json() if d["bookmarked"]] == ["one"]
    assert client.delete("/api/devotions/one/bookmark").json() == {"bookmarked": False}
    assert len(client.get("/api/divine-office/saved").json()) == 1                                                                # the other way round too


@needs_engine
def test_language_narrowing_drops_the_other_language_from_unit_titles(application, engine_on):
    client = user(application, "user_a")
    latin = client.get("/api/divine-office/2026-11-10/compline?language=latin").json()
    english = client.get("/api/divine-office/2026-11-10/compline?language=english").json()
    assert all(u["title_english"] is None and u["title_latin"] for s in latin["sections"] for r in s["rows"] for u in r["units"])
    assert all(u["title_latin"] == "" and u["title_english"] for s in english["sections"] for r in s["rows"] for u in r["units"])
