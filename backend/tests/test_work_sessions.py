from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.db import utcnow
from app.main import create_app
from app.models import Project, ProjectNote, Task, User, WorkSession


def project(client, name="Write the book", **kwargs):
    response = client.post("/api/projects", json={"name": name, **kwargs})
    assert response.status_code == 201, response.text
    return response.json()


def task(client, title="Outline chapter two", **kwargs):
    response = client.post("/api/tasks", json={"title": title, **kwargs})
    assert response.status_code == 201, response.text
    return response.json()


def begin(client, project_id, **kwargs):
    return client.post("/api/work-sessions", json={
        "project_id": project_id, "intention": "Draft the opening", **kwargs,
    })


def backdate(application, session_id, **delta):
    with application.state.session_factory.begin() as db:
        record = db.get(WorkSession, UUID(session_id))
        record.started_at = utcnow() - timedelta(**delta)


def test_begin_a_session_for_a_project(client):
    created = project(client)
    response = begin(client, created["id"], intention="  Draft the opening  ")
    assert response.status_code == 201, response.text
    session = response.json()
    assert session["intention"] == "Draft the opening"
    assert session["status"] == "active"
    assert session["project_id"] == created["id"] and session["project_name"] == "Write the book"
    assert session["task_id"] is None and session["task_title"] is None
    assert session["planned_minutes"] is None
    assert session["started_at"].endswith("Z") and session["ended_at"] is None
    assert session["elapsed_seconds"] is None


@pytest.mark.parametrize("payload", [
    {"intention": ""}, {"intention": "   "}, {"intention": "ok", "planned_minutes": 0},
    {"intention": "ok", "planned_minutes": 9999}, {"intention": "ok", "status": "finished"},
    {"intention": "ok", "user_id": str(uuid4())},
])
def test_begin_validation(client, payload):
    created = project(client)
    response = client.post("/api/work-sessions", json={"project_id": created["id"], **payload})
    assert response.status_code == 422


def test_begin_a_session_for_a_task_with_a_planned_duration(client):
    created = project(client)
    linked = task(client, project_id=created["id"])
    response = begin(client, created["id"], task_id=linked["id"], planned_minutes=45)
    assert response.status_code == 201
    session = response.json()
    assert session["task_id"] == linked["id"] and session["task_title"] == "Outline chapter two"
    assert session["planned_minutes"] == 45


def test_task_must_belong_to_the_project(client):
    mine, other = project(client), project(client, "Other")
    elsewhere = task(client, "Elsewhere", project_id=other["id"])
    loose = task(client, "Loose")
    assert begin(client, mine["id"], task_id=elsewhere["id"]).status_code == 422
    assert begin(client, mine["id"], task_id=loose["id"]).status_code == 422
    assert begin(client, mine["id"], task_id=str(uuid4())).status_code == 404
    assert begin(client, str(uuid4())).status_code == 404
    assert client.get("/api/work-sessions/active").json() is None


def test_only_one_active_session_at_a_time(client, application):
    first, second = project(client), project(client, "Second")
    started = begin(client, first["id"]).json()
    duplicate = begin(client, second["id"])
    assert duplicate.status_code == 409
    assert begin(client, first["id"]).status_code == 409
    assert client.get("/api/work-sessions/active").json()["id"] == started["id"]
    with application.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(WorkSession)) == 1
    # The database refuses a second active row even if the API check were bypassed.
    with pytest.raises(IntegrityError), application.state.session_factory.begin() as db:
        db.add(WorkSession(
            user_id=db.scalar(select(User.id)), project_id=db.scalar(select(Project.id)),
            intention="bypass", status="active",
        ))
    # Finishing frees the slot.
    assert client.post(f"/api/work-sessions/{started['id']}/finish", json={}).status_code == 200
    assert begin(client, second["id"]).status_code == 201


def test_active_session_is_recovered_after_a_refresh(client, application):
    created = project(client)
    started = begin(client, created["id"], planned_minutes=25).json()
    backdate(application, started["id"], minutes=10)
    clone = create_app(application.state.settings)
    with TestClient(clone) as second:
        recovered = second.get("/api/work-sessions/active").json()
    assert recovered["id"] == started["id"] and recovered["status"] == "active"
    assert recovered["planned_minutes"] == 25
    assert recovered["started_at"] != started["started_at"]  # the stored time, not a fresh one
    assert client.get(f"/api/work-sessions/{started['id']}").json()["id"] == started["id"]


def test_finish_saves_notes_and_actual_elapsed_time(client, application):
    created = project(client)
    linked = task(client, project_id=created["id"])
    started = begin(client, created["id"], task_id=linked["id"], planned_minutes=60).json()
    backdate(application, started["id"], minutes=30)
    finished = client.post(f"/api/work-sessions/{started['id']}/finish", json={
        "accomplished": "  Drafted two pages\nand a list  ",
        "resume_note": "Start at the second scene",
    })
    assert finished.status_code == 200, finished.text
    saved = finished.json()
    assert saved["status"] == "finished"
    assert saved["ended_at"].endswith("Z")
    assert 1795 <= saved["elapsed_seconds"] <= 1815
    assert saved["planned_minutes"] == 60
    assert saved["accomplished"] == "Drafted two pages\nand a list"
    assert saved["resume_note"] == "Start at the second scene"
    # Finishing never completes the task and never creates tasks or inbox items.
    assert client.get(f"/api/tasks/{linked['id']}").json()["status"] == "todo"
    assert len(client.get("/api/tasks").json()) == 1 and client.get("/api/inbox").json() == []
    assert client.get("/api/work-sessions/active").json() is None
    assert client.post(f"/api/work-sessions/{started['id']}/finish", json={}).status_code == 409
    assert client.get(f"/api/work-sessions/{started['id']}").json()["accomplished"] == (
        "Drafted two pages\nand a list"
    )


def test_notes_are_optional_and_blank_notes_are_not_stored(client):
    created = project(client)
    started = begin(client, created["id"]).json()
    saved = client.post(f"/api/work-sessions/{started['id']}/finish", json={
        "accomplished": "   ", "resume_note": "",
    }).json()
    assert saved["status"] == "finished"
    assert saved["accomplished"] is None and saved["resume_note"] is None


def test_interrupted_session_invents_no_end_time(client, application):
    created = project(client)
    started = begin(client, created["id"]).json()
    backdate(application, started["id"], hours=30)
    saved = client.post(f"/api/work-sessions/{started['id']}/finish", json={
        "interrupted": True, "resume_note": "Pick the outline back up",
    }).json()
    assert saved["status"] == "interrupted"
    assert saved["ended_at"] is None and saved["elapsed_seconds"] is None
    assert saved["resume_note"] == "Pick the outline back up"
    assert client.get("/api/work-sessions/active").json() is None


def test_project_shows_latest_session_and_latest_nonempty_resume_note(client):
    created = project(client)
    path = f"/api/projects/{created['id']}"
    assert client.get(path).json()["last_session"] is None
    assert client.get(path).json()["resume_session"] is None
    first = begin(client, created["id"], intention="First sitting").json()
    client.post(f"/api/work-sessions/{first['id']}/finish", json={
        "accomplished": "Read the sources", "resume_note": "Open chapter one",
    })
    second = begin(client, created["id"], intention="Second sitting").json()
    assert client.get(path).json()["last_session"]["id"] == first["id"]  # active is not "latest"
    client.post(f"/api/work-sessions/{second['id']}/finish", json={"accomplished": "Wrote notes"})
    detail = client.get(path).json()
    assert detail["last_session"]["id"] == second["id"]
    assert detail["last_session"]["accomplished"] == "Wrote notes"
    assert detail["resume_session"]["id"] == first["id"]
    assert detail["resume_session"]["resume_note"] == "Open chapter one"
    listed = client.get(path + "/work-sessions").json()
    assert [item["id"] for item in listed] == [second["id"], first["id"]]
    third = begin(client, created["id"], intention="In progress").json()
    assert [item["id"] for item in client.get(path + "/work-sessions").json()] == [
        second["id"], first["id"],
    ]
    assert third["status"] == "active"


def test_existing_project_data_is_untouched_by_sessions(client):
    created = project(client, "Keep me", description="The goal", next_action="Old plan")
    path = f"/api/projects/{created['id']}"
    client.post(path + "/notes", json={"content": "A note"})
    client.post(path + "/milestones", json={"title": "A milestone"})
    client.post(path + "/updates", json={
        "summary": "Logged earlier", "next_step": "Keep this next",
    })
    before = client.get(path).json()
    session = begin(client, created["id"], intention="Something else").json()
    client.post(f"/api/work-sessions/{session['id']}/finish", json={
        "accomplished": "Did a thing", "resume_note": "Resume here",
    })
    after = client.get(path).json()
    for field in ("name", "description", "next_action", "last_update", "milestone_count"):
        assert after[field] == before[field], field
    assert after["next_action"] == "Keep this next"
    assert [item["title"] for item in client.get(path + "/history").json()] == ["Logged earlier"]
    assert len(client.get(path + "/notes").json()) == 1


def test_project_and_task_deletion_keep_or_remove_sessions_safely(client, application):
    kept, doomed = project(client, "Kept"), project(client, "Doomed")
    linked = task(client, project_id=kept["id"])
    first = begin(client, kept["id"], task_id=linked["id"]).json()
    client.post(f"/api/work-sessions/{first['id']}/finish", json={"accomplished": "Done"})
    client.delete(f"/api/tasks/{linked['id']}")
    survivor = client.get(f"/api/work-sessions/{first['id']}").json()
    assert survivor["task_id"] is None and survivor["accomplished"] == "Done"
    second = begin(client, doomed["id"]).json()
    client.post(f"/api/work-sessions/{second['id']}/finish", json={})
    assert client.delete(f"/api/projects/{doomed['id']}").status_code == 204
    assert client.get(f"/api/work-sessions/{second['id']}").status_code == 404
    with application.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(WorkSession)) == 1


def test_ownership_isolates_sessions_between_users(client, application):
    own = project(client)
    foreign_user = uuid4()
    with application.state.session_factory.begin() as db:
        db.add(User(id=foreign_user, timezone="UTC"))
        db.flush()
        foreign_project = Project(user_id=foreign_user, name="Private")
        db.add(foreign_project)
        db.flush()
        foreign_task = Task(user_id=foreign_user, project_id=foreign_project.id, title="Secret")
        foreign_session = WorkSession(
            user_id=foreign_user, project_id=foreign_project.id, intention="Secret",
            status="active",
        )
        db.add_all([foreign_task, foreign_session])
        db.flush()
        ids = [str(foreign_project.id), str(foreign_task.id), str(foreign_session.id)]
    project_id, task_id, session_id = ids
    # Another user's active session neither blocks nor leaks into mine.
    assert client.get("/api/work-sessions/active").json() is None
    assert begin(client, own["id"]).status_code == 201
    for method, path, payload in [
        ("post", "/api/work-sessions", {"project_id": project_id, "intention": "x"}),
        ("post", "/api/work-sessions", {
            "project_id": own["id"], "intention": "x", "task_id": task_id,
        }),
        ("get", f"/api/work-sessions/{session_id}", None),
        ("post", f"/api/work-sessions/{session_id}/finish", {}),
        ("get", f"/api/projects/{project_id}/work-sessions", None),
    ]:
        response = client.request(
            method, path, json=payload, headers={"X-User-ID": str(foreign_user)},
        )
        assert response.status_code in (404, 409), (method, path, response.status_code)
        assert response.status_code != 409 or path == "/api/work-sessions", (method, path)
    with application.state.session_factory() as db:
        assert db.get(WorkSession, foreign_session.id).status == "active"


def test_migration_0004_keeps_existing_data_and_round_trips(application):
    created = {}
    with application.state.session_factory.begin() as db:
        user = User(id=uuid4(), timezone="UTC")
        db.add(user)
        db.flush()
        item = Project(user_id=user.id, name="Existing project", description="Keep")
        db.add(item)
        db.flush()
        db.add_all([
            Task(user_id=user.id, project_id=item.id, title="Existing task"),
            ProjectNote(user_id=user.id, project_id=item.id, content="Existing note"),
        ])
        created["project"] = item.id
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with application.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0003")
        assert "work_sessions" not in sa.inspect(connection).get_table_names()
        assert connection.scalar(sa.text("SELECT COUNT(*) FROM projects")) == 1
        command.upgrade(config, "head")
        assert "work_sessions" in sa.inspect(connection).get_table_names()
        assert connection.scalar(sa.text("SELECT name FROM projects")) == "Existing project"
        assert connection.scalar(sa.text("SELECT title FROM tasks")) == "Existing task"
        assert connection.scalar(sa.text("SELECT content FROM project_notes")) == "Existing note"
