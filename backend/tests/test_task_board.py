# ruff: noqa: E501
"""The task board workflow: five statuses over the one existing task system, consistent everywhere."""

from test_api import task


def patch(client, task_id, **body):
    response = client.patch(f"/api/tasks/{task_id}", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_tasks_move_through_all_five_statuses_and_stay_one_record(client):
    created = task(client, "Write the chapter", task_kind="board")
    assert created["status"] == "todo" and created["completed_at"] is None
    for status in ("in_progress", "in_review", "blocked", "todo", "completed"):
        updated = patch(client, created["id"], status=status)
        assert updated["status"] == status
    assert len(client.get("/api/tasks").json()) == 1          # always the same task, never a copy


def test_only_completed_means_done_everywhere(client):
    ids = {status: task(client, f"Task {status}", status=status, task_kind="board")["id"]
           for status in ("todo", "in_progress", "in_review", "blocked")}
    done = task(client, "Task completed", status="completed")
    assert done["completed_at"] is not None
    for status, task_id in ids.items():
        record = client.get(f"/api/tasks/{task_id}").json()
        assert record["completed_at"] is None, f"{status} must not count as completed"
    # Today's "completed today" view agrees: only the completed task appears there.
    today = client.get("/api/today").json()
    titles = [t["title"] for t in today["completed_tasks"]]
    assert titles == ["Task completed"]


def test_completing_from_any_interface_and_reopening_are_symmetric(client):
    created = task(client, "Shared truth", status="in_review", task_kind="board")
    done = patch(client, created["id"], status="completed")       # e.g. ticked off from Today
    assert done["completed_at"] is not None
    reopened = patch(client, created["id"], status="in_progress")  # reopened from the board
    assert reopened["completed_at"] is None and reopened["status"] == "in_progress"


def test_blocking_records_details_and_unblocking_returns_to_previous_status(client):
    created = task(client, "Call the publisher", status="in_progress", task_kind="board")
    blocked = patch(
        client, created["id"], status="blocked",
        blocked_reason="Waiting on a response", waiting_on="The publisher",
        blocked_follow_up="2026-11-20",
    )
    assert blocked["status"] == "blocked"
    assert blocked["previous_status"] == "in_progress"            # remembered automatically
    assert blocked["blocked_reason"] == "Waiting on a response"
    assert blocked["waiting_on"] == "The publisher"
    assert blocked["blocked_follow_up"] == "2026-11-20"
    assert blocked["completed_at"] is None                        # blocked is unfinished
    unblocked = patch(client, created["id"], status=blocked["previous_status"])
    assert unblocked["status"] == "in_progress"
    assert unblocked["blocked_reason"] == "Waiting on a response"  # history kept, not erased


def test_review_stamps_the_submission_once_and_keeps_notes_on_request_changes(client):
    created = task(client, "Draft the essay", status="in_progress", task_kind="board")
    review = patch(client, created["id"], status="in_review",
                   review_notes="Check the citations", reviewer_name="Fr. Doyle")
    assert review["review_requested_at"] is not None
    first_stamp = review["review_requested_at"]
    changes = patch(client, created["id"], status="in_progress")   # Request changes
    assert changes["review_notes"] == "Check the citations"        # notes survive
    again = patch(client, created["id"], status="in_review")
    assert again["review_requested_at"] == first_stamp             # stamped once, not rewritten
    approved = patch(client, created["id"], status="completed")    # Approve -> Done
    assert approved["completed_at"] is not None


def test_board_statuses_filter_and_are_isolated_per_user(client):
    from clerk_tokens import bearer
    task(client, "Mine", status="blocked", task_kind="board")
    other = client.get("/api/tasks?status=blocked", headers=bearer("user_someone_else"))
    assert other.json() == []
    mine = client.get("/api/tasks?status=blocked").json()
    assert [t["title"] for t in mine] == ["Mine"]


def test_old_task_records_remain_usable_without_board_fields(client):
    created = task(client, "Pre-board task")                       # none of the new fields sent
    record = client.get(f"/api/tasks/{created['id']}").json()
    assert record["previous_status"] is None and record["blocked_reason"] is None
    assert record["review_requested_at"] is None
    assert patch(client, created["id"], status="completed")["completed_at"] is not None


def test_every_task_is_a_checklist_item_unless_the_board_created_it(client):
    plain = task(client, "Buy stamps")                              # Daily Checklist default
    assert plain["task_kind"] == "checklist"
    ticket = task(client, "Design the schema", task_kind="board")   # created on the board
    assert ticket["task_kind"] == "board"
    board_only = client.get("/api/tasks?kind=board").json()
    checklist_only = client.get("/api/tasks?kind=checklist").json()
    assert [t["title"] for t in board_only] == ["Design the schema"]
    assert [t["title"] for t in checklist_only] == ["Buy stamps"]
    assert len(client.get("/api/tasks").json()) == 2                # nothing hidden outright


def test_promoting_a_checklist_item_to_the_board_keeps_everything(client):
    item = task(client, "Write thank-you note", due_date="2026-11-20", status="completed")
    moved = patch(client, item["id"], task_kind="board")
    assert moved["task_kind"] == "board"
    assert moved["status"] == "completed" and moved["completed_at"] is not None
    assert moved["due_date"] == "2026-11-20"
    assert moved["id"] == item["id"]                                # same record, never recreated


def test_demoting_a_board_ticket_simplifies_its_workflow_but_keeps_its_substance(client):
    ticket = task(client, "Refactor imports", task_kind="board", status="in_progress",
                  description="Module by module", due_date="2026-11-25")
    blocked = patch(client, ticket["id"], status="blocked", blocked_reason="Waiting on review")
    demoted = patch(client, blocked["id"], task_kind="checklist")
    assert demoted["task_kind"] == "checklist"
    assert demoted["status"] == "todo"                              # mid-workflow becomes plain unfinished
    assert demoted["completed_at"] is None
    assert demoted["description"] == "Module by module"
    assert demoted["due_date"] == "2026-11-25"
    assert demoted["blocked_reason"] == "Waiting on review"         # history kept, not erased
    done = task(client, "Already finished", task_kind="board", status="completed")
    kept = patch(client, done["id"], task_kind="checklist")
    assert kept["status"] == "completed" and kept["completed_at"] is not None


def test_checklist_items_check_off_and_reopen_like_before(client):
    item = task(client, "Water the garden")
    done = patch(client, item["id"], status="completed")
    assert done["completed_at"] is not None
    reopened = patch(client, item["id"], status="todo")
    assert reopened["completed_at"] is None and reopened["task_kind"] == "checklist"


def test_today_shows_scheduled_work_of_either_kind_but_no_unscheduled_board_tickets(client):
    task(client, "Unscheduled ticket", task_kind="board", status="in_progress")
    task(client, "Scheduled ticket", task_kind="board", scheduled_date="2020-01-01")
    task(client, "Overdue errand", scheduled_date="2020-01-01")
    today = client.get("/api/today").json()
    titles = {t["title"] for t in today["previous_tasks"]}
    assert titles == {"Scheduled ticket", "Overdue errand"}         # deliberate scheduling only


def test_the_checklist_is_binary_at_the_api_boundary(client):
    refused = client.post("/api/tasks", json={"title": "Errand", "status": "in_progress"})
    assert refused.status_code == 422                               # checklist items are to do or completed
    item = task(client, "Post the letter")
    for status in ("in_progress", "in_review", "blocked"):
        assert client.patch(f"/api/tasks/{item['id']}", json={"status": status}).status_code == 422
    assert patch(client, item["id"], status="completed")["completed_at"] is not None
    assert patch(client, item["id"], status="todo")["completed_at"] is None
    # The same statuses are fine the moment it is managed on the board.
    promoted = patch(client, item["id"], task_kind="board")
    assert patch(client, promoted["id"], status="in_review")["status"] == "in_review"


def test_an_idea_becomes_a_checklist_item_by_default_and_a_board_ticket_on_request(client):
    idea = client.post("/api/inbox", json={"content": "Compare breviary editions"}).json()
    ticket = client.post(f"/api/inbox/{idea['id']}/convert-to-task", json={"task_kind": "board"}).json()
    assert ticket["task_kind"] == "board" and ticket["status"] == "todo"
    assert ticket["description"] == "Compare breviary editions"
    assert [t["id"] for t in client.get("/api/tasks?kind=board").json()] == [ticket["id"]]
    assert client.get("/api/tasks?kind=checklist").json() == []       # not on the Daily Checklist
    other = client.post("/api/inbox", json={"content": "Buy candles"}).json()
    errand = client.post(f"/api/inbox/{other['id']}/convert-to-task", json={}).json()
    assert errand["task_kind"] == "checklist" and errand["status"] == "todo"


def test_converting_an_idea_preserves_it_and_never_duplicates_the_task(client):
    idea = client.post("/api/inbox", json={"content": "Plan the retreat"}).json()
    first = client.post(f"/api/inbox/{idea['id']}/convert-to-task", json={"task_kind": "board"}).json()
    again = client.post(f"/api/inbox/{idea['id']}/convert-to-task", json={"task_kind": "checklist"}).json()
    assert again["id"] == first["id"]                                 # repeat clicks return the same task
    assert again["task_kind"] == "board"                              # and never re-classify it
    assert len(client.get("/api/tasks").json()) == 1
    kept = client.get(f"/api/inbox/{idea['id']}").json()
    assert kept["status"] == "processed" and kept["content"] == "Plan the retreat"
    assert kept["converted_task_id"] == first["id"]


def test_a_refused_conversion_leaves_the_idea_unchanged(client):
    idea = client.post("/api/inbox", json={"content": "Someday maybe"}).json()
    client.patch(f"/api/inbox/{idea['id']}", json={"status": "archived"})
    refused = client.post(f"/api/inbox/{idea['id']}/convert-to-task", json={"task_kind": "board"})
    assert refused.status_code == 409                                 # restore it first
    kept = client.get(f"/api/inbox/{idea['id']}").json()
    assert kept["status"] == "archived" and kept["converted_task_id"] is None
    assert client.get("/api/tasks").json() == []
