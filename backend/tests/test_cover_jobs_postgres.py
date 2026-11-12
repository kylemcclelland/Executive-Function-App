# ruff: noqa: E501
"""PostgreSQL semantics of the cover-enrichment worker: lease, cooldown and restart behavior.

The ordinary test file exercises the full application; this one exists because a lease must be
proven on PostgreSQL itself (SQLite serialises writers, so it cannot show that two truly
concurrent claims resolve to one winner). It runs only when TEST_DATABASE_URL points at a
disposable PostgreSQL database; it talks straight to the service layer in one dedicated schema,
with only short, immediately committed transactions (Neon terminates connections left idle in a
transaction, which is also why the full-fixture suite is not pointed at it).
"""

import os
import threading
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url

from app.db import Base, make_session_factory
from app.models import Book, CoverEnrichmentJob, User
from app.services import cover_jobs, covers

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="needs a disposable PostgreSQL (TEST_DATABASE_URL)"
)

SCHEMA = "pgtest_cover_jobs"


@pytest.fixture
def pg(monkeypatch):
    url = make_url(os.environ["TEST_DATABASE_URL"]).update_query_dict({"options": f"-csearch_path={SCHEMA}"})
    admin = create_engine(os.environ["TEST_DATABASE_URL"])
    with admin.begin() as c:
        c.execute(text(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE'))
        c.execute(text(f'CREATE SCHEMA "{SCHEMA}"'))
    engine = create_engine(url.render_as_string(hide_password=False), pool_pre_ping=True)
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    state = {"now": datetime.now(UTC)}
    monkeypatch.setattr(covers, "utcnow", lambda: state["now"])
    monkeypatch.setattr(covers, "PACER", covers.Pacer(4.0, clock=lambda: 0.0, sleep=lambda s: None))
    with factory.begin() as db:
        user = User(timezone="UTC")
        db.add(user)
        db.flush()
        user_id = user.id
        for i in range(4):
            db.add(Book(user_id=user_id, title=f"B{i}", isbn_13=f"97800000{i:04d}0"))
    print(f"dialect={engine.dialect.name} driver={engine.dialect.driver} "
          f"database={engine.url.database} schema={SCHEMA}")
    yield {"factory": factory, "user_id": user_id, "clock": state, "engine": engine}
    engine.dispose()
    with admin.begin() as c:
        c.execute(text(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE'))
    admin.dispose()


def job_row(factory):
    with factory() as db:
        job = db.scalar(select(CoverEnrichmentJob))
        db.expunge(job)
        return job


def test_exactly_one_of_many_truly_concurrent_claims_wins(pg, monkeypatch):
    factory, user_id = pg["factory"], pg["user_id"]
    cover_jobs.start_job(factory, user_id)
    job_id = job_row(factory).id
    now = covers.utcnow()
    results, barrier = [], threading.Barrier(6)

    def contender():
        barrier.wait()      # all six issue the conditional UPDATE at the same moment
        results.append(cover_jobs.claim_job(factory, job_id, now))

    threads = [threading.Thread(target=contender) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(True) == 1 and results.count(False) == 5
    # While the lease is held, a whole worker pass must not touch the job either.
    calls = []
    monkeypatch.setattr(covers, "lookup_cover", lambda isbn: calls.append(isbn) or covers.Lookup(covers.FOUND))
    assert cover_jobs.run_due_jobs(factory)["jobs_run"] == 0 and calls == []
    # A crashed holder's lease expires on its own and the job is recoverable.
    pg["clock"]["now"] += timedelta(seconds=cover_jobs.CLAIM_SECONDS + 1)
    assert cover_jobs.run_due_jobs(factory)["jobs_run"] == 1


def test_a_paused_job_is_never_claimed(pg, monkeypatch):
    factory, user_id = pg["factory"], pg["user_id"]
    cover_jobs.start_job(factory, user_id)
    cover_jobs.set_status(factory, user_id, cover_jobs.PAUSED)
    calls = []
    monkeypatch.setattr(covers, "lookup_cover", lambda isbn: calls.append(isbn) or covers.Lookup(covers.FOUND))
    assert not cover_jobs.claim_job(factory, job_row(factory).id, covers.utcnow())
    assert cover_jobs.run_due_jobs(factory) == {"jobs_run": 0, "batches": 0, "found": 0}
    assert calls == []


def test_cooldown_persists_across_invocations_and_resumes_without_repeat_lookups(pg, monkeypatch):
    factory, user_id, clock = pg["factory"], pg["user_id"], pg["clock"]
    first = {"status": covers.RATE_LIMITED}
    calls = []

    def scripted(isbn):
        calls.append(isbn)
        if first["status"]:
            status, first["status"] = first["status"], None
            return covers.Lookup(status, retry_after=600.0, http_status=429)
        return covers.Lookup(covers.FOUND)

    monkeypatch.setattr(covers, "lookup_cover", scripted)
    cover_jobs.start_job(factory, user_id)
    cover_jobs.run_due_jobs(factory)
    held = job_row(factory)
    assert held.status == "running" and held.next_run_at > covers.utcnow()
    assert len(calls) == 1
    # A completely fresh "process" (new engine, new pool) sees the same persisted pause...
    fresh = make_session_factory(create_engine(pg["engine"].url.render_as_string(hide_password=False)))
    assert cover_jobs.run_due_jobs(fresh)["batches"] == 0 and len(calls) == 1
    # ...and continues on its own once the cooldown has passed: no browser, no click.
    clock["now"] += timedelta(seconds=700)
    cover_jobs.run_due_jobs(fresh)
    done = job_row(factory)
    assert done.status == "done" and done.covers_found == 4
    # Restarting the job answers everything from the cache: not one further request.
    before = len(calls)
    cover_jobs.start_job(factory, user_id)
    cover_jobs.run_due_jobs(factory)
    assert len(calls) == before and job_row(factory).status == "done"
