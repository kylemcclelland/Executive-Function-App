# ruff: noqa: E501, F811
"""Automatic, resumable cover enrichment: the job survives restarts and resumes by itself."""

import urllib.error
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import select
from test_cover_rate_limits import Script, clock, isbn13, make_book, sleeps  # noqa: F401

from app.models import Book, CoverEnrichmentJob
from app.services import cover_jobs, covers


def http_error(code, retry_after=None):
    headers = {"Retry-After": retry_after} if retry_after is not None else {}
    return urllib.error.HTTPError("https://covers.openlibrary.org", code, "msg", headers, None)


def auto(client, action=""):
    if action:
        response = client.post(f"/api/books/covers/auto/{action}")
    else:
        response = client.get("/api/books/covers/auto")
    assert response.status_code == 200, response.text
    return response.json()


def worker(application, batches=5, rng=lambda: 0.5):
    return cover_jobs.run_due_jobs(application.state.session_factory, batches, rng)


def book_covers(client):
    books = client.get("/api/books?page_size=100").json()["items"]
    return {b["title"]: b["cover_url"] for b in books}


def test_a_started_job_processes_batches_and_finishes_without_further_requests(
    client, application, monkeypatch, sleeps, clock
):
    a, b = isbn13(1), isbn13(2)
    make_book(client, "Found", isbn_13=a)
    make_book(client, "Missing", isbn_13=b)
    monkeypatch.setattr(covers, "lookup_cover", Script({a: covers.FOUND}))
    status = auto(client, "start")
    assert status["status"] == "running" and status["remaining"] == 2
    summary = worker(application)
    assert summary == {"jobs_run": 1, "batches": 1, "found": 1}
    status = auto(client)
    assert status["status"] == "done"
    assert status["covers_found"] == 1 and status["without_cover"] == 1
    assert status["remaining"] == 0 and status["next_run_at"] is None
    assert book_covers(client)["Found"] is not None
    # Done means done: another pass makes no request at all.
    script = Script()
    monkeypatch.setattr(covers, "lookup_cover", script)
    assert worker(application) == {"jobs_run": 0, "batches": 0, "found": 0}
    assert script.calls == []


def test_a_429_reschedules_for_after_retry_after_and_resumes_automatically(
    client, application, monkeypatch, sleeps, clock
):
    a, b = isbn13(3), isbn13(4)
    make_book(client, "First", isbn_13=a)
    make_book(client, "Second", isbn_13=b)
    monkeypatch.setattr(
        covers, "lookup_cover",
        Script({a: covers.Lookup(covers.RATE_LIMITED, retry_after=600.0, http_status=429)}),
    )
    auto(client, "start")
    worker(application)
    status = auto(client)
    assert status["status"] == "running" and status["waiting"] is True
    resume_at = status["next_run_at"]
    with application.state.session_factory() as db:
        blocked = covers.active_cooldown(db, covers.utcnow())
    assert (blocked - covers.utcnow()).total_seconds() == pytest.approx(600, abs=2)
    # While cooling down, a worker pass touches nothing.
    script = Script({a: covers.FOUND, b: covers.FOUND})
    monkeypatch.setattr(covers, "lookup_cover", script)
    assert worker(application)["batches"] == 0 and script.calls == []
    # After the cooldown the next scheduled pass simply continues: no click, no browser.
    clock["now"] += timedelta(seconds=700)
    summary = worker(application)
    assert summary["found"] == 2 and script.calls == [a, b]
    assert auto(client)["status"] == "done"
    assert resume_at is not None


def test_a_503_backs_off_exponentially_with_bounded_jitter(client, application, monkeypatch, sleeps, clock):
    a = isbn13(5)
    make_book(client, "Patient", isbn_13=a)
    monkeypatch.setattr(covers, "lookup_cover", Script({a: covers.Lookup(covers.UNAVAILABLE, http_status=503)}))
    auto(client, "start")
    waits = []
    for expected_streak in (1, 2, 3):
        worker(application, rng=lambda: 1.0)   # jitter at its upper bound
        with application.state.session_factory() as db:
            job = db.scalar(select(CoverEnrichmentJob))
            assert job.unavailable_streak == expected_streak
            waits.append((job.next_run_at - covers.utcnow()).total_seconds())
        clock["now"] = job.next_run_at + timedelta(seconds=1)
    # 60 s, 120 s, 240 s bases, each at +20% jitter; the service's own 60 s floor never exceeds them.
    assert waits == pytest.approx([72, 144, 288], abs=3)
    assert cover_jobs.backoff_seconds(99, rng=lambda: 1.0) == pytest.approx(3600 * 1.2)
    assert cover_jobs.backoff_seconds(1, rng=lambda: 0.0) == pytest.approx(48)


def test_repeated_network_errors_pause_the_job_with_the_reason_recorded(
    client, application, monkeypatch, sleeps, clock
):
    a = isbn13(6)
    make_book(client, "Unlucky", isbn_13=a)
    monkeypatch.setattr(covers, "lookup_cover", Script({a: covers.Lookup(covers.ERROR)}))
    auto(client, "start")
    for _ in range(cover_jobs.MAX_RETRIES):
        worker(application)
        status = auto(client)
        if status["status"] == "paused":
            break
        clock["now"] += timedelta(hours=2)
    assert status["status"] == "paused" and "Paused after" in status["last_error"]
    # Paused means paused: no pass touches it, however long it waits.
    script = Script()
    monkeypatch.setattr(covers, "lookup_cover", script)
    clock["now"] += timedelta(days=1)
    assert worker(application)["jobs_run"] == 0 and script.calls == []


def test_progress_survives_a_worker_restart(client, application, monkeypatch, sleeps, clock):
    isbns = [isbn13(i) for i in range(10, 18)]
    for i, isbn in enumerate(isbns):
        make_book(client, f"Book {i}", isbn_13=isbn)
    monkeypatch.setattr(covers, "lookup_cover", Script(default=covers.FOUND))
    auto(client, "start")
    worker(application, batches=1)             # one batch (≤5 requests), then the process "dies"
    first = auto(client)
    assert 0 < first["covers_found"] < len(isbns)
    # A brand-new pass (fresh invocation, same database) continues from the job row.
    worker(application, batches=5)
    status = auto(client)
    assert status["status"] == "done" and status["covers_found"] == len(isbns)
    assert all(url is not None for url in book_covers(client).values())


def test_two_concurrent_passes_cannot_run_the_same_job(client, application, monkeypatch, sleeps, clock):
    a = isbn13(20)
    make_book(client, "Contended", isbn_13=a)
    auto(client, "start")
    with application.state.session_factory() as db:
        job_id = db.scalar(select(CoverEnrichmentJob.id))
    # The first claim wins; the second, made while the lease is held, must lose.
    assert cover_jobs.claim_job(application.state.session_factory, job_id, covers.utcnow())
    script = Script(default=covers.FOUND)
    monkeypatch.setattr(covers, "lookup_cover", script)
    assert worker(application)["jobs_run"] == 0 and script.calls == []
    # An expired lease is claimable again: a crashed pass cannot wedge the job forever.
    clock["now"] += timedelta(seconds=cover_jobs.CLAIM_SECONDS + 1)
    assert worker(application)["jobs_run"] == 1


def test_no_cover_answers_are_cached_and_not_asked_again(client, application, monkeypatch, sleeps, clock):
    a = isbn13(21)
    make_book(client, "Coverless", isbn_13=a)
    script = Script({a: covers.NOT_FOUND})
    monkeypatch.setattr(covers, "lookup_cover", script)
    auto(client, "start")
    worker(application)
    assert auto(client)["status"] == "done" and script.calls == [a]
    # Restarting the job within the not-found TTL answers from the cache: zero requests.
    auto(client, "start")
    worker(application)
    assert script.calls == [a]
    assert auto(client)["status"] == "done"


def test_pause_and_resume_by_hand(client, application, monkeypatch, sleeps, clock):
    a, b = isbn13(22), isbn13(23)
    make_book(client, "One", isbn_13=a)
    make_book(client, "Two", isbn_13=b)
    script = Script(default=covers.FOUND)
    monkeypatch.setattr(covers, "lookup_cover", script)
    auto(client, "start")
    assert auto(client, "pause")["status"] == "paused"
    assert worker(application)["jobs_run"] == 0 and script.calls == []
    assert auto(client, "resume")["status"] == "running"
    worker(application)
    status = auto(client)
    assert status["status"] == "done" and status["covers_found"] == 2
    # Pausing a job that never existed is a clean 404, not a crash.
    from clerk_tokens import bearer
    assert client.post("/api/books/covers/auto/pause", headers=bearer("user_without_job")).status_code == 404


def test_a_failed_request_discards_no_completed_work(client, application, monkeypatch, sleeps, clock):
    good, bad = isbn13(24), isbn13(25)
    make_book(client, "AAA kept", isbn_13=good)       # sorts first: processed before the failure
    make_book(client, "ZZZ blocked", isbn_13=bad)
    monkeypatch.setattr(
        covers, "lookup_cover",
        Script({good: covers.FOUND, bad: covers.Lookup(covers.RATE_LIMITED, retry_after=60.0, http_status=429)}),
    )
    auto(client, "start")
    worker(application)
    assert book_covers(client)["AAA kept"] is not None     # persisted before the 429 arrived
    status = auto(client)
    assert status["status"] == "running" and status["covers_found"] == 1


def test_existing_covers_and_cached_lookups_are_preserved(client, application, monkeypatch, sleeps, clock):
    kept = make_book(client, "Chosen", isbn_13=isbn13(26), cover_url="https://example.org/mine.jpg")
    monkeypatch.setattr(covers, "lookup_cover", Script(default=covers.FOUND))
    auto(client, "start")
    worker(application)
    with application.state.session_factory() as db:
        assert db.get(Book, UUID(kept["id"])).cover_url == "https://example.org/mine.jpg"
