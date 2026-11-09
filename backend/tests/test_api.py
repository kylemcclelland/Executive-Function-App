from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select

from app.core.config import Settings
from app.main import create_app
from app.models import DailyPriority, InboxItem, Step, Task, User


def task(client, title="A task", **kwargs):
    response = client.post("/api/tasks", json={"title": title, **kwargs})
    assert response.status_code == 201, response.text
    return response.json()


def inbox(client, content="A thought"):
    response = client.post("/api/inbox", json={"content": content})
    assert response.status_code == 201, response.text
    return response.json()


def test_health_and_local_cors(client):
    assert client.get("/health").json() == {"status": "ok"}
    allowed = client.options("/api/tasks", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
    })
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    denied = client.options("/api/tasks", headers={
        "Origin": "https://untrusted.example", "Access-Control-Request-Method": "POST",
    })
    assert "access-control-allow-origin" not in denied.headers


def test_task_crud_all_fields_completion_and_reopen(client):
    project = client.post("/api/projects", json={"name": "Lunch"}).json()["id"]
    created = task(
        client, "  Plan lunch  ", project_id=project, description="Details",
        due_date="2026-11-08", scheduled_date="2026-11-07",
        estimated_minutes=15, next_action="Open menu",
    )
    assert created["title"] == "Plan lunch"
    assert created["project_id"] == project
    assert created["steps"] == []
    assert created["created_at"].endswith("Z")
    assert created["completed_at"] is None
    path = f"/api/tasks/{created['id']}"
    assert client.get(path).json() == created
    completed = client.patch(path, json={"status": "completed"}).json()
    assert completed["completed_at"].endswith("Z")
    assert client.patch(path, json={"status": "completed"}).json()["completed_at"] == (
        completed["completed_at"]
    )
    reopened = client.patch(path, json={
        "status": "in_progress", "description": None, "project_id": None,
        "due_date": None, "scheduled_date": None, "estimated_minutes": None,
        "next_action": None, "title": "New title",
    }).json()
    assert reopened["completed_at"] is None
    assert reopened["description"] is None
    assert reopened["title"] == "New title"
    assert len(client.get("/api/tasks?status=in_progress").json()) == 1
    assert client.get("/api/tasks?status=completed").json() == []
    assert client.delete(path).status_code == 204
    assert client.get(path).status_code == 404
    assert client.get("/api/tasks").json() == []


@pytest.mark.parametrize("payload", [
    {"title": ""}, {"title": "   "}, {"title": "ok", "estimated_minutes": 0},
    {"title": "ok", "status": "unknown"}, {"title": "ok", "user_id": str(uuid4())},
    {"title": "ok", "due_date": "not-a-date"},
])
def test_task_input_validation(client, payload):
    assert client.post("/api/tasks", json=payload).status_code == 422


def test_explicit_null_required_fields_rejected(client):
    created = task(client)
    for field in ("title", "status"):
        assert client.patch(f"/api/tasks/{created['id']}", json={field: None}).status_code == 422


def test_steps_complete_edit_reorder_delete(client):
    created = task(client)
    path = f"/api/tasks/{created['id']}"
    steps = [
        client.post(path + "/steps", json={"title": title}).json()
        for title in ("one", "two", "three")
    ]
    assert [step["position"] for step in steps] == [0, 1, 2]
    moved = client.patch(path + f"/steps/{steps[2]['id']}", json={
        "position": 0, "title": "first", "is_completed": True,
    })
    assert moved.status_code == 200
    assert moved.json()["is_completed"]
    actual = client.get(path).json()["steps"]
    assert [step["title"] for step in actual] == ["first", "one", "two"]
    assert [step["position"] for step in actual] == [0, 1, 2]
    assert client.delete(path + f"/steps/{steps[0]['id']}").status_code == 204
    actual = client.get(path).json()["steps"]
    assert [step["position"] for step in actual] == [0, 1]
    assert client.get(path).json()["status"] == "todo"
    inserted = client.post(path + "/steps", json={"title": "middle", "position": 1})
    assert inserted.status_code == 201
    assert [step["title"] for step in client.get(path).json()["steps"]] == [
        "first", "middle", "two",
    ]
    assert client.patch(path + f"/steps/{steps[1]['id']}", json={"position": -1}).status_code == 422
    assert client.patch(path + f"/steps/{steps[1]['id']}", json={"title": None}).status_code == 422
    assert client.patch(path + f"/steps/{uuid4()}", json={"title": "x"}).status_code == 404


def test_inbox_edit_archive_restore_delete(client):
    capture = inbox(client, "  original\n text  ")
    path = f"/api/inbox/{capture['id']}"
    assert capture["content"] == "  original\n text  "
    assert capture["status"] == "unprocessed"
    assert client.patch(path, json={"status": "processed"}).status_code == 409
    assert client.patch(path, json={"content": "edited"}).json()["content"] == "edited"
    archived = client.patch(path, json={"status": "archived"}).json()
    assert archived["archived_at"].endswith("Z")
    assert client.get("/api/inbox?status=unprocessed").json() == []
    assert client.post(path + "/convert-to-task").status_code == 409
    restored = client.patch(path, json={"status": "unprocessed"}).json()
    assert restored["archived_at"] is None
    assert client.delete(path).status_code == 204
    assert client.get(path).status_code == 404
    assert client.get("/api/inbox").json() == []


@pytest.mark.parametrize("content", ["", "   ", "\n\t"])
def test_blank_inbox_rejected(client, content):
    assert client.post("/api/inbox", json={"content": content}).status_code == 422


def test_conversion_is_idempotent_and_preserves_capture(client):
    original = "  Buy groceries\n and prepare dinner  "
    capture = inbox(client, original)
    path = f"/api/inbox/{capture['id']}"
    first = client.post(path + "/convert-to-task", json={"title": "Dinner"}).json()
    retry = client.post(path + "/convert-to-task", json={"title": "Different"}).json()
    assert retry["id"] == first["id"]
    assert client.post(path + "/convert").json()["id"] == first["id"]
    assert retry["title"] == "Dinner"
    assert first["description"] == original
    assert client.get(path).json()["content"] == original
    assert client.get(path).json()["status"] == "processed"
    assert client.get(path).json()["converted_task_id"] == first["id"]
    assert len(client.get("/api/tasks").json()) == 1
    assert client.patch(path, json={"content": "rewritten"}).status_code == 409
    assert client.patch(path, json={"status": "archived"}).json()["status"] == "archived"
    assert client.post(path + "/convert-to-task").json()["id"] == first["id"]
    assert client.patch(path, json={"status": "unprocessed"}).json()["status"] == "processed"
    client.patch(path, json={"status": "archived"})
    assert client.patch(path, json={"status": "processed"}).json()["archived_at"] is None
    assert client.delete(f"/api/tasks/{first['id']}").status_code == 204
    assert client.post(path + "/convert-to-task").status_code == 409
    client.patch(path, json={"status": "archived"})
    assert client.patch(path, json={"status": "unprocessed"}).json()["status"] == "processed"
    assert client.post(path + "/convert-to-task").status_code == 409
    assert client.get("/api/tasks").json() == []


def test_conversion_optional_body_and_default_title(client):
    capture = inbox(client, "  First line\nSecond line  ")
    converted = client.post(f"/api/inbox/{capture['id']}/convert-to-task")
    assert converted.status_code == 200
    assert converted.json()["title"] == "First line\nSecond line"


def test_today_max_three_order_and_no_task_mutation(client, application):
    tasks = [task(client, f"task {index}") for index in range(4)]
    before = client.get("/api/tasks").json()
    ordered = [tasks[index]["id"] for index in (2, 0, 1)]
    result = client.put("/api/today/priorities", json={"task_ids": ordered})
    assert result.status_code == 200
    assert [item["id"] for item in result.json()["priorities"]] == ordered
    assert client.put("/api/today/priorities", json={
        "task_ids": [item["id"] for item in tasks],
    }).status_code == 422
    assert client.put("/api/today/priorities", json={
        "task_ids": [ordered[0], ordered[0]],
    }).status_code == 422
    assert client.put("/api/today/priorities", json={"task_ids": [str(uuid4())]}).status_code == 404
    assert [item["id"] for item in client.get("/api/today").json()["priorities"]] == ordered
    assert client.get("/api/tasks").json() == before
    with application.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(DailyPriority)) == 3
    assert client.put("/api/today/priorities", json={"task_ids": []}).json()["priorities"] == []


def test_today_timezone_previous_day_separation_and_completed(client, monkeypatch, application):
    import app.api.routes as routes
    import app.services.today as today_service
    monkeypatch.setattr(routes, "utcnow", lambda: datetime(2026, 11, 6, 1, 30, tzinfo=UTC))
    monkeypatch.setattr(today_service, "utcnow", routes.utcnow)
    assert client.patch("/api/user", json={"timezone": "America/Los_Angeles"}).status_code == 200
    assert client.get("/api/today").json()["date"] == "2026-11-05"
    old = task(client, "Yesterday", scheduled_date="2026-11-04")
    prior = task(client, "Old priority")
    today = task(client, "Today's selection", scheduled_date="2026-11-05")
    done = task(client, "Finished")
    with application.state.session_factory.begin() as db:
        user = db.scalar(select(User))
        db.add(DailyPriority(user_id=user.id, priority_date=date(2026, 11, 4),
                             task_id=UUID(prior["id"]), position=0))
    assert client.patch(f"/api/tasks/{done['id']}", json={"status": "completed"}).status_code == 200
    inbox(client)
    archived = inbox(client)
    client.patch(f"/api/inbox/{archived['id']}", json={"status": "archived"})
    before = client.get("/api/tasks").json()
    view = client.put("/api/today/priorities", json={"task_ids": [today["id"]]}).json()
    assert view["timezone"] == "America/Los_Angeles"
    assert {item["id"] for item in view["previous_tasks"]} == {old["id"], prior["id"]}
    assert [item["id"] for item in view["completed_tasks"]] == [done["id"]]
    assert view["inbox_count"] == 1
    assert client.get("/api/tasks").json() == before
    monkeypatch.setattr(routes, "utcnow", lambda: datetime(2026, 11, 6, 9, 30, tzinfo=UTC))
    monkeypatch.setattr(today_service, "utcnow", routes.utcnow)
    next_day = client.get("/api/today").json()
    assert next_day["date"] == "2026-11-06"
    assert next_day["priorities"] == []
    assert {item["id"] for item in next_day["previous_tasks"]} == {
        old["id"], prior["id"], today["id"],
    }
    assert next_day["completed_tasks"] == []
    client.put("/api/today/priorities", json={"task_ids": [old["id"]]})
    with application.state.session_factory() as db:
        dates = db.scalars(
            select(DailyPriority.priority_date).order_by(DailyPriority.priority_date)
        ).all()
        assert dates == [date(2026, 11, 4), date(2026, 11, 5), date(2026, 11, 6)]


def test_timezone_validation(client):
    assert client.patch("/api/user", json={"timezone": "Invalid/Zone"}).status_code == 422
    assert client.patch("/api/user", json={"timezone": "../UTC"}).status_code == 422
    assert client.get("/api/user").json()["timezone"] == "UTC"


def test_ownership_every_mutation_and_request_identity_ignored(client, application):
    own = task(client)
    foreign_user = uuid4()
    with application.state.session_factory.begin() as db:
        db.add(User(id=foreign_user, timezone="UTC"))
        db.flush()
        foreign_task = Task(user_id=foreign_user, title="Private task")
        db.add(foreign_task)
        db.flush()
        foreign_step = Step(task_id=foreign_task.id, title="Secret", position=0)
        capture = InboxItem(user_id=foreign_user, content="Private capture")
        db.add_all([foreign_step, capture])
        db.flush()
        ids = str(foreign_task.id), str(foreign_step.id), str(capture.id)
    task_id, step_id, item_id = ids
    headers = {"X-User-ID": str(foreign_user)}
    assert [item["id"] for item in client.get("/api/tasks", headers=headers).json()] == [own["id"]]
    assert client.get("/api/inbox", headers=headers).json() == []
    operations = [
        ("get", f"/api/tasks/{task_id}", None),
        ("patch", f"/api/tasks/{task_id}", {"title": "stolen"}),
        ("delete", f"/api/tasks/{task_id}", None),
        ("post", f"/api/tasks/{task_id}/steps", {"title": "stolen"}),
        ("patch", f"/api/tasks/{task_id}/steps/{step_id}", {"is_completed": True}),
        ("delete", f"/api/tasks/{task_id}/steps/{step_id}", None),
        ("patch", f"/api/tasks/{own['id']}/steps/{step_id}", {"position": 0}),
        ("get", f"/api/inbox/{item_id}", None),
        ("patch", f"/api/inbox/{item_id}", {"content": "stolen"}),
        ("delete", f"/api/inbox/{item_id}", None),
        ("post", f"/api/inbox/{item_id}/convert-to-task", {}),
        ("put", "/api/today/priorities", {"task_ids": [task_id]}),
    ]
    for method, path, payload in operations:
        response = client.request(method, path, json=payload, headers=headers)
        assert response.status_code == 404, (method, path, response.text)
    assert client.post("/api/inbox", json={
        "content": "valid", "user_id": str(foreign_user),
    }).status_code == 422
    assert client.get("/api/today").json()["inbox_count"] == 0
    with application.state.session_factory() as db:
        assert db.get(Task, foreign_task.id).title == "Private task"
        assert db.get(InboxItem, capture.id).content == "Private capture"


def test_persistence_across_application_instances(client, application):
    created = task(client)
    capture = inbox(client)
    clone = create_app(application.state.settings)
    with TestClient(clone) as second:
        assert second.get(f"/api/tasks/{created['id']}").json()["title"] == "A task"
        assert second.get(f"/api/inbox/{capture['id']}").json()["content"] == "A thought"
        assert second.get("/api/user").json()["id"] == client.get("/api/user").json()["id"]


@pytest.mark.parametrize("method,path,payload", [
    ("POST", "/api/tasks", {"title": "Must not be acknowledged"}),
    ("POST", "/api/inbox", {"content": "Must not be acknowledged"}),
    ("PUT", "/api/today/priorities", {"task_ids": []}),
])
def test_commit_failure_never_returns_success(application, method, path, payload):
    def reject_commit(session):
        raise RuntimeError("Simulated commit failure")

    factory = application.state.session_factory
    event.listen(factory, "before_commit", reject_commit)
    try:
        with TestClient(application, raise_server_exceptions=False) as client:
            response = client.request(method, path, json=payload)
            assert response.status_code == 500
    finally:
        event.remove(factory, "before_commit", reject_commit)
    with TestClient(application) as client:
        assert client.get("/api/tasks").json() == []
        assert client.get("/api/inbox").json() == []
        assert client.get("/api/today").json()["priorities"] == []


def test_production_refuses_to_start_without_clerk():
    with pytest.raises(RuntimeError, match="Clerk"):
        create_app(Settings(app_env="production", _env_file=None))


def test_missing_environment_defaults_to_fail_closed(monkeypatch):
    for name in ("APP_ENV", "CLERK_SECRET_KEY", "CLERK_JWT_KEY"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)
    assert settings.app_env == "production"
    with pytest.raises(RuntimeError, match="Clerk"):
        create_app(settings)


@pytest.mark.parametrize("origins", [
    "http://localhost:5173,http://127.0.0.1:5173",
    '["http://localhost:5173","http://127.0.0.1:5173"]',
])
def test_infrastructure_environment_config(monkeypatch, origins):
    monkeypatch.setenv("CORS_ORIGINS", origins)
    monkeypatch.setenv("USER_TIMEZONE", "America/New_York")
    settings = Settings(_env_file=None)
    assert settings.dev_user_timezone == "America/New_York"
    assert settings.cors_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]


def test_task_delete_cascades_steps_and_priorities(client, application):
    created = task(client)
    client.post(f"/api/tasks/{created['id']}/steps", json={"title": "step"})
    client.put("/api/today/priorities", json={"task_ids": [created["id"]]})
    assert client.delete(f"/api/tasks/{created['id']}").status_code == 204
    assert client.get("/api/today").json()["priorities"] == []
    with application.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Step)) == 0
        assert db.scalar(select(func.count()).select_from(DailyPriority)) == 0


def test_dst_completion_boundaries(client, monkeypatch, application):
    import app.services.today as today_service
    monkeypatch.setattr(
        today_service, "utcnow", lambda: datetime(2026, 11, 1, 18, tzinfo=UTC),
    )
    client.patch("/api/user", json={"timezone": "America/New_York"})
    # November 1 is a 25-hour local day: [04:00Z November 1, 05:00Z November 2).
    instants = [
        datetime(2026, 11, 1, 3, 59, tzinfo=UTC),
        datetime(2026, 11, 1, 4, tzinfo=UTC),
        datetime(2026, 11, 2, 4, 59, tzinfo=UTC),
        datetime(2026, 11, 2, 5, tzinfo=UTC),
    ]
    with application.state.session_factory.begin() as db:
        user = db.scalar(select(User))
        db.add_all([
            Task(user_id=user.id, title=str(index), status="completed", completed_at=instant)
            for index, instant in enumerate(instants)
        ])
    assert [item["title"] for item in client.get("/api/today").json()["completed_tasks"]] == [
        "1", "2",
    ]


def test_concurrent_conversion_has_one_task(client, application):
    from concurrent.futures import ThreadPoolExecutor
    if application.state.engine.dialect.name != "postgresql":
        pytest.skip("Concurrency requires PostgreSQL row locking")
    capture = inbox(client)
    path = f"/api/inbox/{capture['id']}/convert-to-task"
    with ThreadPoolExecutor(max_workers=4) as workers:
        responses = list(workers.map(lambda _: client.post(path), range(4)))
    assert all(response.status_code == 200 for response in responses)
    assert len({response.json()["id"] for response in responses}) == 1
    assert len(client.get("/api/tasks").json()) == 1


def test_concurrent_priority_updates_are_atomic(client, application):
    from concurrent.futures import ThreadPoolExecutor
    if application.state.engine.dialect.name != "postgresql":
        pytest.skip("Concurrency requires PostgreSQL row locking")
    tasks = [task(client, str(index)) for index in range(6)]
    choices = [
        [item["id"] for item in tasks[:3]],
        [item["id"] for item in tasks[3:]],
    ]
    with ThreadPoolExecutor(max_workers=2) as workers:
        responses = list(workers.map(
            lambda ids: client.put("/api/today/priorities", json={"task_ids": ids}),
            choices,
        ))
    assert all(response.status_code == 200 for response in responses)
    assert [item["id"] for item in client.get("/api/today").json()["priorities"]] in choices
