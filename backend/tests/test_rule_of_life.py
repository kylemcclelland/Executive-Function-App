# ruff: noqa: E501
"""Rule of Life: scheduling, validation, recurrence across daylight saving time, completion marks, user isolation and the honest notification status."""

from datetime import date, datetime, time
from uuid import UUID, uuid4

from clerk_tokens import bearer
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_devotions import add_devotion

from app.models import RuleOfLifeEntry, SavedOfficeUnit, User


def user(application, name):
    return TestClient(application, headers=bearer(name))


def save_office_prayer(application, client, title="Psalm 11"):
    """A saved Divine Office prayer owned by the client's user (inserted directly: the engine is not needed to test scheduling)."""
    client.get("/api/user")                                              # makes sure the user row exists
    with application.state.session_factory.begin() as db:
        owner = db.scalars(select(User).order_by(User.created_at.desc())).first()
        row = SavedOfficeUnit(user_id=owner.id, unit_key=f"psalm:{uuid4().hex[:16]}", kind="psalm", title_latin="Psalmus 11", title_english=title, source_hour="compline",
                              source_date=date(2026, 11, 10), content={}, source={})
        db.add(row)
        db.flush()
        return str(row.id)


def legacy_entry(application, client, saved_id, local_time="07:00"):
    """An entry created before saved Office prayers were withdrawn from the Rule of Life (the API no longer creates them)."""
    client.get("/api/user")
    with application.state.session_factory.begin() as db:
        owner = db.get(SavedOfficeUnit, UUID(saved_id)).user_id
        entry = RuleOfLifeEntry(user_id=owner, kind="saved_office", ref=saved_id, title="Psalm 11", local_time=time.fromisoformat(local_time), timezone="America/New_York",
                                recurrence="daily", weekdays=[], start_date=date(2026, 11, 1), notify=False, active=True, fingerprint=f"saved_office|{saved_id}|{local_time}|daily||")
        db.add(entry)
        db.flush()
        return str(entry.id)


def create(client, **fields):
    body = {"kind": "office_hour", "ref": "compline", "local_time": "21:00", "timezone": "America/New_York", "recurrence": "daily", "start_date": "2026-11-01", **fields}
    return client.post("/api/rule-of-life", json=body)


def test_create_edit_pause_and_delete_an_entry(application):
    client = user(application, "user_a")
    created = create(client, notify=True)
    assert created.status_code == 201
    entry = created.json()
    assert (entry["title"], entry["local_time"], entry["recurrence"], entry["notify"], entry["active"], entry["available"]) == ("Compline", "21:00", "daily", True, True, True)
    assert entry["link"] == "/divine-office?date=2026-11-01&hour=compline"
    edited = client.patch(f"/api/rule-of-life/{entry['id']}", json={"local_time": "20:30", "recurrence": "weekly", "weekdays": [0, 2, 4], "notify": False}).json()
    assert (edited["local_time"], edited["recurrence"], edited["weekdays"], edited["notify"]) == ("20:30", "weekly", [0, 2, 4], False)
    paused = client.patch(f"/api/rule-of-life/{entry['id']}", json={"active": False}).json()
    assert paused["active"] is False and paused["local_time"] == "20:30"
    assert client.get("/api/rule-of-life/occurrences", params={"start": "2026-11-01", "end": "2026-11-30"}).json() == []         # a paused entry has no occurrences
    assert client.delete(f"/api/rule-of-life/{entry['id']}").status_code == 204
    assert client.get("/api/rule-of-life").json() == [] and client.delete(f"/api/rule-of-life/{entry['id']}").status_code == 404


def test_only_office_hours_and_listed_devotions_can_be_added(application):
    client = user(application, "user_a")
    saved_id = save_office_prayer(application, client)
    add_devotion(application, "holy-rosary", title="The Holy Rosary")
    rosary = create(client, kind="devotion", ref="holy-rosary", local_time="18:00").json()
    assert (rosary["title"], rosary["link"]) == ("The Holy Rosary", "/devotions/holy-rosary")
    assert create(client, kind="office_hour", ref="lauds", local_time="07:00").status_code == 201
    assert create(client, kind="devotion", ref="missing", local_time="19:00").status_code == 404
    assert create(client, kind="office_hour", ref="midnight", local_time="19:00").status_code == 422
    assert create(client, kind="saved_office", ref=saved_id, local_time="20:00").status_code == 422          # withdrawn: no new schedule can reference a saved prayer
    assert create(client, kind="whatever", ref="x").status_code == 422
    assert [e["local_time"] for e in client.get("/api/rule-of-life").json()] == ["07:00", "18:00"]               # in chronological order


def test_all_eight_hours_can_be_scheduled(application):
    client = user(application, "user_a")
    for slug in ("matins", "lauds", "prime", "terce", "sext", "none", "vespers", "compline"):
        assert create(client, ref=slug).status_code == 201, slug
    found = client.get("/api/rule-of-life/occurrences", params={"start": "2026-11-10", "end": "2026-11-10"}).json()
    assert sorted(o["title"] for o in found) == sorted(["Matins", "Lauds", "Prime", "Terce", "Sext", "None", "Vespers", "Compline"])


def test_a_legacy_saved_prayer_entry_is_preserved_shown_scheduled_and_editable(application):
    client = user(application, "user_a")
    saved_id = save_office_prayer(application, client)
    entry_id = legacy_entry(application, client, saved_id)
    listed = client.get("/api/rule-of-life").json()
    assert [(e["kind"], e["link"], e["available"]) for e in listed] == [("saved_office", f"/divine-office/saved/{saved_id}", True)]
    found = client.get("/api/rule-of-life/occurrences", params={"start": "2026-11-10", "end": "2026-11-10"}).json()
    assert [(o["entry_id"], o["link"]) for o in found] == [(entry_id, f"/divine-office/saved/{saved_id}")]
    assert client.patch(f"/api/rule-of-life/{entry_id}", json={"local_time": "08:30"}).json()["local_time"] == "08:30"      # time and recurrence stay editable
    assert client.put(f"/api/rule-of-life/{entry_id}/occurrences/2026-11-10", json={"status": "completed"}).status_code == 200
    assert client.patch(f"/api/rule-of-life/{entry_id}", json={"kind": "devotion"}).status_code == 422                        # the reference itself cannot be changed
    assert client.delete(f"/api/rule-of-life/{entry_id}").status_code == 204
    with application.state.session_factory() as db:
        assert db.get(SavedOfficeUnit, UUID(saved_id)) is not None                                                            # removing the schedule keeps the saved prayer


def test_duplicates_are_refused_but_distinct_schedules_are_allowed(application):
    client = user(application, "user_a")
    assert create(client).status_code == 201
    assert create(client).status_code == 409                                                       # the same prayer, time and recurrence
    assert create(client, local_time="21:30").status_code == 201                                   # another time
    assert create(client, recurrence="weekly", weekdays=[6]).status_code == 201                    # another recurrence
    assert create(client, recurrence="once", start_date="2026-11-10").status_code == 201
    other = create(client, local_time="22:00").json()
    assert client.patch(f"/api/rule-of-life/{other['id']}", json={"local_time": "21:00"}).status_code == 409     # editing into a duplicate
    assert len(client.get("/api/rule-of-life").json()) == 5


def test_server_side_validation(application):
    client = user(application, "user_a")
    assert create(client, timezone="Mars/Olympus").status_code == 422
    assert create(client, local_time="25:00").status_code == 422
    assert create(client, recurrence="weekly", weekdays=[]).status_code == 422
    assert create(client, recurrence="weekly", weekdays=[7]).status_code == 422
    assert create(client, recurrence="once", start_date=None).status_code == 422
    assert create(client, extra="field").status_code == 422
    assert client.get("/api/rule-of-life/occurrences", params={"start": "2026-01-01", "end": "2027-01-01"}).status_code == 422       # an over-long window


def test_weekly_and_one_time_occurrences_and_each_hours_own_date(application):
    client = user(application, "user_a")
    create(client, recurrence="weekly", weekdays=[0, 2], local_time="08:00", kind="office_hour", ref="lauds")            # Mondays and Wednesdays
    create(client, recurrence="once", start_date="2026-11-12", local_time="12:00", ref="sext", kind="office_hour")
    found = client.get("/api/rule-of-life/occurrences", params={"start": "2026-11-09", "end": "2026-11-15"}).json()
    assert [(o["date"], o["local_time"], o["title"]) for o in found] == [("2026-11-09", "08:00", "Lauds"), ("2026-11-11", "08:00", "Lauds"), ("2026-11-12", "12:00", "Sext")]
    assert [o["link"] for o in found] == ["/divine-office?date=2026-11-09&hour=lauds", "/divine-office?date=2026-11-11&hour=lauds", "/divine-office?date=2026-11-12&hour=sext"]
    assert client.get("/api/rule-of-life/occurrences", params={"start": "2026-11-16", "end": "2026-11-22"}).json()[0]["date"] == "2026-11-16"       # the one-time prayer does not recur


def test_a_daily_prayer_keeps_its_local_time_across_daylight_saving_changes(application):
    client = user(application, "user_a")
    create(client, local_time="07:00", recurrence="daily", start_date="2026-03-01", ref="prime", timezone="America/New_York")
    found = client.get("/api/rule-of-life/occurrences", params={"start": "2026-03-07", "end": "2026-03-09"}).json()
    assert [(o["date"], o["local_time"], o["start"][11:16]) for o in found] == [("2026-03-07", "07:00", "12:00"), ("2026-03-08", "07:00", "11:00"), ("2026-03-09", "07:00", "11:00")]     # clocks change on 8 March
    again = client.get("/api/rule-of-life/occurrences", params={"start": "2026-10-31", "end": "2026-11-02"}).json()
    assert [(o["date"], o["start"][11:16]) for o in again] == [("2026-10-31", "11:00"), ("2026-11-01", "12:00"), ("2026-11-02", "12:00")]                                                   # and back at 2 a.m. on 1 November
    assert all(datetime.fromisoformat(o["start"]).utcoffset().total_seconds() == 0 for o in found)


def test_the_time_zone_is_the_entrys_own(application):
    client = user(application, "user_a")
    create(client, local_time="07:00", timezone="Asia/Tokyo", recurrence="once", start_date="2026-11-10")
    only = client.get("/api/rule-of-life/occurrences", params={"start": "2026-11-09", "end": "2026-11-11"}).json()
    assert [(o["date"], o["time_zone"], o["start"][:16]) for o in only] == [("2026-11-10", "Asia/Tokyo", "2026-11-09T22:00")]


def test_completed_and_skipped_marks_are_idempotent_and_only_on_scheduled_dates(application):
    client = user(application, "user_a")
    entry = create(client, recurrence="weekly", weekdays=[1]).json()                            # Tuesdays
    url = f"/api/rule-of-life/{entry['id']}/occurrences"
    assert client.put(f"{url}/2026-11-10", json={"status": "completed"}).json()["status"] == "completed"
    assert client.put(f"{url}/2026-11-10", json={"status": "completed"}).status_code == 200
    assert client.put(f"{url}/2026-11-10", json={"status": "skipped"}).json()["status"] == "skipped"
    with application.state.session_factory() as db:
        assert len(db.scalars(select(RuleOfLifeEntry)).all()) == 1
    assert [o["status"] for o in client.get("/api/rule-of-life/occurrences", params={"start": "2026-11-10", "end": "2026-11-17"}).json()] == ["skipped", None]
    assert client.put(f"{url}/2026-11-11", json={"status": "completed"}).status_code == 422       # a Wednesday: not scheduled
    assert client.put(f"{url}/2026-11-10", json={"status": "streak"}).status_code == 422
    assert client.delete(f"{url}/2026-11-10").status_code == 204
    assert client.get("/api/rule-of-life/occurrences", params={"start": "2026-11-10", "end": "2026-11-10"}).json()[0]["status"] is None


def test_each_user_sees_and_changes_only_their_own_entries_and_prayers(application):
    a, b = user(application, "user_a"), user(application, "user_b")
    saved_id = save_office_prayer(application, a)
    mine = {"id": legacy_entry(application, a, saved_id)}
    assert b.get("/api/rule-of-life").json() == []
    assert b.get("/api/rule-of-life/occurrences", params={"start": "2026-11-01", "end": "2026-11-30"}).json() == []
    assert b.patch(f"/api/rule-of-life/{mine['id']}", json={"active": False}).status_code == 404
    assert b.delete(f"/api/rule-of-life/{mine['id']}").status_code == 404
    assert b.put(f"/api/rule-of-life/{mine['id']}/occurrences/2026-11-10", json={"status": "completed"}).status_code == 404
    assert len(a.get("/api/rule-of-life").json()) == 1


def test_a_removed_saved_prayer_leaves_a_legacy_entry_marked_unavailable_not_broken(application):
    client = user(application, "user_a")
    saved_id = save_office_prayer(application, client)
    legacy_entry(application, client, saved_id)
    with application.state.session_factory.begin() as db:
        db.delete(db.get(SavedOfficeUnit, __import__("uuid").UUID(saved_id)))
    assert [e["available"] for e in client.get("/api/rule-of-life").json()] == [False]


def test_notification_preference_is_stored_and_delivery_is_reported_as_unavailable(application):
    client = user(application, "user_a")
    assert create(client, notify=True).json()["notify"] is True and create(client, local_time="22:00").json()["notify"] is False
    assert client.get("/api/rule-of-life/notifications").json()["delivery"] == "unavailable"


def test_everything_needs_sign_in(application):
    anonymous = TestClient(application, headers={})
    assert anonymous.get("/api/rule-of-life").status_code == 401
    assert anonymous.post("/api/rule-of-life", json={}).status_code == 401
