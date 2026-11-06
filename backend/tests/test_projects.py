from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import create_app
from app.models import Milestone, Project, ProjectNote, ProjectUpdate, Task, User


def project(client, name="Write the book", **kwargs):
    response = client.post("/api/projects", json={"name": name, **kwargs})
    assert response.status_code == 201, response.text
    return response.json()


def task(client, title="A task", **kwargs):
    response = client.post("/api/tasks", json={"title": title, **kwargs})
    assert response.status_code == 201, response.text
    return response.json()


def test_create_with_only_a_name_and_edit(client):
    created = project(client, "  Learn piano  ")
    assert created["name"] == "Learn piano"
    assert created["status"] == "active"
    assert created["description"] is None and created["target_date"] is None
    assert created["open_task_count"] == 0 and created["milestone_count"] == 0
    assert created["last_update"] is None and created["archived_at"] is None
    path = f"/api/projects/{created['id']}"
    edited = client.patch(path, json={
        "name": "Learn jazz piano", "description": "Play one standard", "category": " Music ",
        "target_date": "2027-03-01", "next_action": "Find a lesson book",
    }).json()
    assert edited["category"] == "Music"
    assert edited["target_date"] == "2027-03-01"
    cleared = client.patch(path, json={"description": "  ", "target_date": None}).json()
    assert cleared["description"] is None and cleared["target_date"] is None
    assert cleared["next_action"] == "Find a lesson book"
    assert client.get(path).json() == cleared


@pytest.mark.parametrize("payload", [
    {"name": ""}, {"name": "   "}, {"name": "ok", "status": "failed"},
    {"name": "ok", "user_id": str(uuid4())}, {"name": "ok", "target_date": "soon"},
    {"name": "ok", "category": "x" * 101},
])
def test_project_input_validation(client, payload):
    assert client.post("/api/projects", json=payload).status_code == 422


def test_null_required_project_fields_rejected(client):
    created = project(client)
    for field in ("name", "status", "archived"):
        response = client.patch(f"/api/projects/{created['id']}", json={field: None})
        assert response.status_code == 422


def test_status_completion_archive_search_and_filters(client):
    active = project(client, "Garden", category="Home", description="Raised beds")
    paused = project(client, "Taxes", status="paused")
    someday = project(client, "Learn Japanese", status="someday")
    path = f"/api/projects/{active['id']}"

    def names(query=""):
        return sorted(item["name"] for item in client.get(f"/api/projects{query}").json())

    assert names() == ["Garden", "Learn Japanese", "Taxes"]
    assert names("?status=paused") == ["Taxes"]
    assert names("?status=someday") == ["Learn Japanese"]
    assert names("?q=raised") == ["Garden"]
    assert names("?q=HOME") == ["Garden"]
    assert names("?q=%25") == []
    assert client.get("/api/projects?status=failed").status_code == 422

    done = client.patch(path, json={"status": "completed"}).json()
    assert done["completed_at"].endswith("Z")
    assert client.patch(path, json={"status": "completed"}).json()["completed_at"] == (
        done["completed_at"]
    )
    reopened = client.patch(path, json={"status": "active"}).json()
    assert reopened["completed_at"] is None

    archived = client.patch(path, json={"archived": True}).json()
    assert archived["archived_at"].endswith("Z")
    assert names() == ["Learn Japanese", "Taxes"]
    assert names("?archived=true") == ["Garden"]
    assert client.patch(path, json={"archived": False}).json()["archived_at"] is None
    assert names("?archived=true") == []
    assert paused["status"] == "paused" and someday["status"] == "someday"


def test_delete_project_keeps_tasks_and_removes_project_data(client, application):
    created = project(client)
    path = f"/api/projects/{created['id']}"
    milestone = client.post(path + "/milestones", json={"title": "Draft"}).json()
    client.post(path + "/notes", json={"content": "Research"})
    client.post(path + "/updates", json={"summary": "Started"})
    kept = task(client, "Outline", project_id=created["id"], milestone_id=milestone["id"])
    assert client.delete(path).status_code == 204
    assert client.get(path).status_code == 404
    survivor = client.get(f"/api/tasks/{kept['id']}").json()
    assert survivor["title"] == "Outline"
    assert survivor["project_id"] is None and survivor["milestone_id"] is None
    assert survivor["project_position"] is None
    with application.state.session_factory() as db:
        for model in (Milestone, ProjectNote, ProjectUpdate):
            assert db.scalar(select(func.count()).select_from(model)) == 0


def test_tasks_link_without_duplicating_records(client, application):
    mine = project(client)
    other = project(client, "Other project")
    path = f"/api/projects/{mine['id']}"
    first, second, loose = task(client, "First"), task(client, "Second"), task(client, "Loose")
    linked = client.post(path + "/tasks", json={"task_ids": [first["id"], second["id"]]})
    assert linked.status_code == 200
    assert [item["id"] for item in linked.json()] == [first["id"], second["id"]]
    assert all(item["project_name"] == "Write the book" for item in linked.json())
    again = client.post(path + "/tasks", json={"task_ids": [first["id"]]}).json()
    assert [item["id"] for item in again] == [first["id"], second["id"]]
    assert len(client.get("/api/tasks").json()) == 3
    with application.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Task)) == 3

    summary = client.get("/api/projects").json()[0]
    assert summary["open_task_count"] == 2 and summary["next_task_title"] == "First"
    assert client.get(f"/api/tasks/{loose['id']}").json()["project_id"] is None

    moved = client.post(
        f"/api/projects/{other['id']}/tasks", json={"task_ids": [first["id"]]},
    ).json()
    assert [item["id"] for item in moved] == [first["id"]]
    assert [item["id"] for item in client.get(path + "/tasks").json()] == [second["id"]]

    unlinked = client.patch(f"/api/tasks/{second['id']}", json={"project_id": None}).json()
    assert unlinked["project_id"] is None and unlinked["project_name"] is None
    assert client.get(path + "/tasks").json() == []
    assert client.post(path + "/tasks", json={"task_ids": [str(uuid4())]}).status_code == 404
    duplicate = client.post(path + "/tasks", json={"task_ids": [loose["id"], loose["id"]]})
    assert duplicate.status_code == 422


def test_create_task_inside_project_and_reorder(client):
    created = project(client)
    path = f"/api/projects/{created['id']}"
    ids = [
        task(client, title, project_id=created["id"])["id"] for title in ("One", "Two", "Three")
    ]
    assert [item["id"] for item in client.get(path + "/tasks").json()] == ids
    reordered = client.put(
        path + "/tasks/order", json={"task_ids": [ids[2], ids[0]]},
    ).json()
    assert [item["id"] for item in reordered] == [ids[2], ids[0], ids[1]]
    assert [item["project_position"] for item in reordered] == [0, 1, 2]
    assert [item["id"] for item in client.get(path + "/tasks").json()] == [ids[2], ids[0], ids[1]]
    assert client.put(path + "/tasks/order", json={"task_ids": [str(uuid4())]}).status_code == 404


def test_task_completion_is_shared_by_projects_and_today(client):
    created = project(client, next_action="Open the manuscript")
    path = f"/api/projects/{created['id']}"
    chosen = task(client, "Draft chapter", project_id=created["id"])
    task(client, "Edit chapter", project_id=created["id"])
    client.put("/api/today/priorities", json={"task_ids": [chosen["id"]]})

    today = client.get("/api/today").json()
    assert today["priorities"][0]["project_name"] == "Write the book"
    assert [item["name"] for item in today["active_projects"]] == ["Write the book"]
    assert today["active_projects"][0]["open_task_count"] == 2
    assert today["active_projects"][0]["next_action"] == "Open the manuscript"

    client.patch(f"/api/tasks/{chosen['id']}", json={"status": "completed"})
    summary = client.get(path).json()
    assert summary["open_task_count"] == 1 and summary["completed_task_count"] == 1
    assert summary["next_task_title"] == "Edit chapter"
    today = client.get("/api/today").json()
    assert [item["id"] for item in today["completed_tasks"]] == [chosen["id"]]
    assert today["active_projects"][0]["open_task_count"] == 1
    history = client.get(path + "/history").json()
    assert [(item["type"], item["title"]) for item in history] == [
        ("task_completed", "Draft chapter"),
    ]
    client.patch(f"/api/tasks/{chosen['id']}", json={"status": "todo"})
    assert client.get(path + "/history").json() == []
    assert client.get(path).json()["open_task_count"] == 2


def test_paused_and_someday_projects_stay_off_today(client):
    project(client, "Active one")
    project(client, "Paused one", status="paused")
    project(client, "Someday one", status="someday")
    archived = project(client, "Archived one")
    client.patch(f"/api/projects/{archived['id']}", json={"archived": True})
    names = [item["name"] for item in client.get("/api/today").json()["active_projects"]]
    assert names == ["Active one"]


def test_notes_persist_search_edit_delete(client, application):
    created = project(client)
    path = f"/api/projects/{created['id']}/notes"
    first = client.post(path, json={"title": " Sources ", "content": "Chapter 1\n  keep spacing"})
    assert first.status_code == 201
    note = first.json()
    assert note["title"] == "Sources" and note["content"] == "Chapter 1\n  keep spacing"
    plain = client.post(path, json={"content": "Remember the interview"}).json()
    assert plain["title"] is None
    clone = create_app(application.state.settings)
    with TestClient(clone) as second:
        listed = second.get(path).json()
        assert {item["id"] for item in listed} == {note["id"], plain["id"]}
    assert [item["id"] for item in client.get(path + "?q=INTERVIEW").json()] == [plain["id"]]
    assert [item["id"] for item in client.get(path + "?q=sources").json()] == [note["id"]]
    assert client.get(path + "?q=nothing").json() == []
    edited = client.patch(f"{path}/{note['id']}", json={"content": "Updated", "title": None}).json()
    assert edited["id"] == note["id"] and edited["title"] is None and edited["content"] == "Updated"
    assert client.patch(f"{path}/{note['id']}", json={"content": None}).status_code == 422
    assert client.patch(f"{path}/{note['id']}", json={"content": "  "}).status_code == 422
    assert client.post(path, json={"content": "   "}).status_code == 422
    assert client.delete(f"{path}/{note['id']}").status_code == 204
    assert client.delete(f"{path}/{note['id']}").status_code == 404
    assert [item["id"] for item in client.get(path).json()] == [plain["id"]]


def test_milestones_persist_progress_and_task_association(client, application):
    created = project(client)
    path = f"/api/projects/{created['id']}"
    draft = client.post(path + "/milestones", json={
        "title": "First draft", "description": "All chapters", "target_date": "2027-01-15",
    }).json()
    revise = client.post(path + "/milestones", json={"title": "Revision"}).json()
    assert [draft["position"], revise["position"]] == [0, 1]
    one = task(client, "Chapter one", project_id=created["id"], milestone_id=draft["id"])
    two = task(client, "Chapter two", project_id=created["id"], milestone_id=draft["id"])
    task(client, "Unrelated", project_id=created["id"])
    client.patch(f"/api/tasks/{one['id']}", json={"status": "completed"})

    clone = create_app(application.state.settings)
    with TestClient(clone) as second:
        listed = second.get(path + "/milestones").json()
    assert [item["title"] for item in listed] == ["First draft", "Revision"]
    assert listed[0]["task_count"] == 2 and listed[0]["completed_task_count"] == 1
    assert listed[0]["target_date"] == "2027-01-15"

    done = client.patch(f"{path}/milestones/{draft['id']}", json={"completed": True}).json()
    assert done["completed_at"].endswith("Z")
    assert client.get(path).json()["milestones_completed"] == 1
    assert client.get(path).json()["milestone_count"] == 2
    assert "milestone_completed" in [item["type"] for item in client.get(path + "/history").json()]
    reopened = client.patch(
        f"{path}/milestones/{draft['id']}", json={"completed": False, "title": "Draft 1"},
    ).json()
    assert reopened["completed_at"] is None and reopened["title"] == "Draft 1"
    assert client.patch(
        f"{path}/milestones/{draft['id']}", json={"title": None},
    ).status_code == 422

    moved = client.patch(f"/api/tasks/{two['id']}", json={"milestone_id": revise["id"]}).json()
    assert moved["milestone_id"] == revise["id"]
    cleared = client.patch(f"/api/tasks/{two['id']}", json={"milestone_id": None}).json()
    assert cleared["milestone_id"] is None
    assert client.delete(f"{path}/milestones/{draft['id']}").status_code == 204
    assert client.get(f"/api/tasks/{one['id']}").json()["milestone_id"] is None
    assert client.get(f"/api/tasks/{one['id']}").json()["project_id"] == created["id"]


def test_milestone_must_belong_to_the_tasks_project(client):
    mine, other = project(client), project(client, "Other")
    foreign = client.post(f"/api/projects/{other['id']}/milestones", json={"title": "X"}).json()
    own = client.post(f"/api/projects/{mine['id']}/milestones", json={"title": "Y"}).json()
    created = task(client, "Linked", project_id=mine["id"], milestone_id=own["id"])
    assert client.patch(
        f"/api/tasks/{created['id']}", json={"milestone_id": foreign["id"]},
    ).status_code == 404
    assert client.post("/api/tasks", json={
        "title": "Orphan", "milestone_id": own["id"],
    }).status_code == 422
    switched = client.patch(f"/api/tasks/{created['id']}", json={"project_id": other["id"]}).json()
    assert switched["milestone_id"] is None
    assert switched["project_id"] == other["id"]


def test_session_logs_persist_and_set_next_action(client, application):
    created = project(client, next_action="Old plan")
    path = f"/api/projects/{created['id']}"
    session = client.post(path + "/updates", json={
        "kind": "session", "summary": "  Wrote the outline  ", "next_step": "Draft section one",
    })
    assert session.status_code == 201
    progress = client.post(
        path + "/updates", json={"kind": "progress", "summary": "Halfway"},
    ).json()
    assert session.json()["summary"] == "Wrote the outline"
    detail = client.get(path).json()
    assert detail["next_action"] == "Draft section one"
    assert detail["last_update"]["id"] == progress["id"]
    clone = create_app(application.state.settings)
    with TestClient(clone) as second:
        updates = second.get(path + "/updates").json()
        history = second.get(path + "/history").json()
    assert [item["id"] for item in updates] == [progress["id"], session.json()["id"]]
    assert [(item["type"], item["title"]) for item in history] == [
        ("progress", "Halfway"), ("session", "Wrote the outline"),
    ]
    assert history[1]["next_step"] == "Draft section one"
    assert client.post(path + "/updates", json={"summary": "  "}).status_code == 422
    assert client.post(path + "/updates", json={"summary": "x", "kind": "bad"}).status_code == 422
    assert client.delete(f"{path}/updates/{progress['id']}").status_code == 204
    assert client.delete(f"{path}/updates/{progress['id']}").status_code == 404
    assert client.get(path).json()["last_update"]["id"] == session.json()["id"]


def test_recent_activity_orders_projects_for_resuming(client):
    older, newer = project(client, "Older"), project(client, "Newer")
    assert [item["name"] for item in client.get("/api/projects").json()] == ["Newer", "Older"]
    client.post(f"/api/projects/{older['id']}/updates", json={"summary": "Back at it"})
    assert [item["name"] for item in client.get("/api/projects").json()] == ["Older", "Newer"]
    assert newer["id"]


def test_ownership_prevents_cross_user_access(client, application):
    own_project = project(client)
    own_task = task(client, "Mine", project_id=own_project["id"])
    foreign_user = uuid4()
    with application.state.session_factory.begin() as db:
        db.add(User(id=foreign_user, timezone="UTC"))
        db.flush()
        foreign = Project(user_id=foreign_user, name="Private project")
        db.add(foreign)
        db.flush()
        foreign_milestone = Milestone(
            user_id=foreign_user, project_id=foreign.id, title="Secret",
        )
        foreign_note = ProjectNote(user_id=foreign_user, project_id=foreign.id, content="Secret")
        foreign_update = ProjectUpdate(
            user_id=foreign_user, project_id=foreign.id, summary="Secret",
        )
        foreign_task = Task(user_id=foreign_user, title="Private task", project_id=foreign.id)
        db.add_all([foreign_milestone, foreign_note, foreign_update, foreign_task])
        db.flush()
        ids = [
            str(item.id) for item in
            (foreign, foreign_milestone, foreign_note, foreign_update, foreign_task)
        ]
    project_id, milestone_id, note_id, update_id, task_id = ids
    base = f"/api/projects/{project_id}"
    own = f"/api/projects/{own_project['id']}"
    headers = {"X-User-ID": str(foreign_user)}
    operations = [
        ("get", base, None), ("patch", base, {"name": "stolen"}), ("delete", base, None),
        ("get", base + "/tasks", None), ("post", base + "/tasks", {"task_ids": [own_task["id"]]}),
        ("put", base + "/tasks/order", {"task_ids": []}),
        ("get", base + "/milestones", None), ("post", base + "/milestones", {"title": "x"}),
        ("patch", f"{base}/milestones/{milestone_id}", {"title": "stolen"}),
        ("delete", f"{base}/milestones/{milestone_id}", None),
        ("get", base + "/notes", None), ("post", base + "/notes", {"content": "x"}),
        ("patch", f"{base}/notes/{note_id}", {"content": "stolen"}),
        ("delete", f"{base}/notes/{note_id}", None),
        ("get", base + "/updates", None), ("post", base + "/updates", {"summary": "x"}),
        ("delete", f"{base}/updates/{update_id}", None), ("get", base + "/history", None),
        ("patch", f"{own}/milestones/{milestone_id}", {"title": "stolen"}),
        ("patch", f"{own}/notes/{note_id}", {"content": "stolen"}),
        ("delete", f"{own}/updates/{update_id}", None),
        ("post", own + "/tasks", {"task_ids": [task_id]}),
        ("patch", f"/api/tasks/{own_task['id']}", {"project_id": project_id}),
        ("post", "/api/tasks", {"title": "x", "project_id": project_id}),
        ("patch", f"/api/tasks/{own_task['id']}", {"milestone_id": milestone_id}),
    ]
    for method, path, payload in operations:
        response = client.request(method, path, json=payload, headers=headers)
        assert response.status_code == 404, (method, path, response.status_code)
    assert [item["id"] for item in client.get("/api/projects", headers=headers).json()] == [
        own_project["id"],
    ]
    assert client.get("/api/today").json()["active_projects"][0]["id"] == own_project["id"]
    unchanged = client.get(f"/api/tasks/{own_task['id']}").json()
    assert unchanged["project_id"] == own_project["id"] and unchanged["milestone_id"] is None
    with application.state.session_factory() as db:
        assert db.get(Project, foreign.id).name == "Private project"
        assert db.get(Task, foreign_task.id).project_id == foreign.id
        assert db.get(Milestone, foreign_milestone.id).title == "Secret"
        assert db.get(ProjectNote, foreign_note.id).content == "Secret"
        assert db.scalar(select(func.count()).select_from(ProjectUpdate)) == 1


def test_migration_keeps_existing_tasks_and_their_project_links(application):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    user, other_user = uuid4(), uuid4()
    shared, solo = uuid4(), uuid4()
    task_ids = {name: uuid4() for name in ("a", "b", "c", "d")}
    with application.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0002")
        now = datetime.now(UTC)
        def stamps():
            return [sa.column("created_at", sa.DateTime(timezone=True)),
                    sa.column("updated_at", sa.DateTime(timezone=True))]

        users = sa.table(
            "users", sa.column("id", sa.Uuid()), sa.column("timezone", sa.String()), *stamps(),
        )
        tasks = sa.table(
            "tasks", sa.column("id", sa.Uuid()), sa.column("user_id", sa.Uuid()),
            sa.column("project_id", sa.Uuid()), sa.column("title", sa.String()),
            sa.column("status", sa.String()), *stamps(),
        )
        connection.execute(sa.insert(users), [
            {"id": user, "timezone": "UTC", "created_at": now, "updated_at": now},
            {"id": other_user, "timezone": "UTC", "created_at": now, "updated_at": now},
        ])
        rows = [
            ("a", user, shared), ("b", user, shared), ("c", user, solo), ("d", other_user, shared),
        ]
        connection.execute(sa.insert(tasks), [
            {"id": task_ids[name], "user_id": owner, "project_id": link, "title": name,
             "status": "todo", "created_at": now, "updated_at": now}
            for name, owner, link in rows
        ])
        command.upgrade(config, "head")
    with application.state.session_factory() as db:
        loaded = {name: db.get(Task, task_id) for name, task_id in task_ids.items()}
        assert {name: task.title for name, task in loaded.items()} == {
            "a": "a", "b": "b", "c": "c", "d": "d",
        }
        assert loaded["a"].project_id == loaded["b"].project_id == shared
        assert loaded["c"].project_id == solo
        assert loaded["d"].project_id is None
        recovered = db.get(Project, shared)
        assert recovered.user_id == user and recovered.name == "Untitled project"
        assert db.get(Project, solo).user_id == user
    with application.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0002")
        assert connection.scalar(sa.text("SELECT COUNT(*) FROM tasks")) == 4
        command.upgrade(config, "head")
