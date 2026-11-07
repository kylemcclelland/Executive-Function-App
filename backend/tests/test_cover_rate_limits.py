import email.utils
import os
import sqlite3
import threading
import urllib.error
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import create_app
from app.models import Book, CoverLookup, CoverServiceState, Note, NoteLink, User
from app.services import covers


def isbn13(seed: int) -> str:
    body = f"978{seed:09d}"
    total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(body))
    return body + str((10 - total % 10) % 10)


def make_book(client, title, **kwargs):
    response = client.post("/api/books", json={"title": title, **kwargs})
    assert response.status_code == 201, response.text
    return response.json()


def enrich(client, **body):
    response = client.post("/api/books/covers/enrich", json=body)
    assert response.status_code == 200, response.text
    return response.json()


class Script:
    """A scripted stand-in for Open Library that records every request."""

    def __init__(self, outcomes=None, default=covers.NOT_FOUND):
        self.outcomes, self.default, self.calls = outcomes or {}, default, []

    def __call__(self, isbn):
        self.calls.append(isbn)
        outcome = self.outcomes.get(isbn, self.default)
        return outcome if isinstance(outcome, covers.Lookup) else covers.Lookup(outcome)


@pytest.fixture
def sleeps(monkeypatch):
    """Replace the pacer's clock so pacing is observable without real waiting."""
    recorded: list[float] = []
    monkeypatch.setattr(
        covers,
        "PACER",
        covers.Pacer(covers.REQUEST_INTERVAL_SECONDS, clock=lambda: 0.0, sleep=recorded.append),
    )
    return recorded


@pytest.fixture(autouse=True)
def no_live_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("Tests must not reach Open Library")

    monkeypatch.setattr(covers.urllib.request, "urlopen", refuse)


@pytest.fixture
def clock(monkeypatch):
    """A controllable UTC clock for the cover service and the missing-covers route."""
    state = {"now": datetime.now(UTC)}
    monkeypatch.setattr(covers, "utcnow", lambda: state["now"])
    monkeypatch.setattr("app.api.routes.book_import.utcnow", lambda: state["now"])
    return state


def http_error(code, retry_after=None):
    headers = {"Retry-After": retry_after} if retry_after is not None else {}
    return urllib.error.HTTPError("https://covers.openlibrary.org", code, "msg", headers, None)


# ------------------------------------------------------------------ Retry-After and pacing


def test_retry_after_understands_seconds_and_http_dates():
    now = datetime(2026, 11, 6, 12, 0, 0, tzinfo=UTC)
    assert covers.parse_retry_after("120", now) == 120.0
    assert covers.parse_retry_after("  45 ", now) == 45.0
    assert covers.parse_retry_after("0", now) == 0.0
    later = email.utils.format_datetime(now + timedelta(seconds=90), usegmt=True)
    assert covers.parse_retry_after(later, now) == pytest.approx(90.0)
    past = email.utils.format_datetime(now - timedelta(hours=1), usegmt=True)
    assert covers.parse_retry_after(past, now) == 0.0
    assert covers.parse_retry_after("Fri, 06 Nov 2026 12:03:00 GMT", now) == pytest.approx(180.0)
    for junk in (None, "", "   ", "soon", "-5", "12.5", "Someday, maybe"):
        assert covers.parse_retry_after(junk, now) is None, junk


@pytest.mark.parametrize("code", [429, 503])
def test_lookup_reads_retry_after_from_the_response(monkeypatch, code):
    expected = covers.RATE_LIMITED if code == 429 else covers.UNAVAILABLE

    def fake(request, timeout=None):
        raise http_error(code, "120")

    monkeypatch.setattr(covers.urllib.request, "urlopen", fake)
    result = covers.lookup_cover(isbn13(1))
    assert result == covers.Lookup(expected, 120.0, http_status=code)

    when = email.utils.format_datetime(datetime.now(UTC) + timedelta(seconds=300), usegmt=True)
    monkeypatch.setattr(
        covers.urllib.request,
        "urlopen",
        lambda r, timeout=None: (_ for _ in ()).throw(http_error(code, when)),
    )
    dated = covers.lookup_cover(isbn13(1))
    assert dated.status == expected and 295 <= dated.retry_after <= 300

    monkeypatch.setattr(
        covers.urllib.request,
        "urlopen",
        lambda r, timeout=None: (_ for _ in ()).throw(http_error(code)),
    )
    assert covers.lookup_cover(isbn13(1)) == covers.Lookup(expected, None, http_status=code)


def test_the_default_pace_is_one_request_every_four_seconds():
    # 4 s keeps a run at 75 requests per 5 minutes, under Open Library's 100-per-IP cap.
    assert covers.REQUEST_INTERVAL_SECONDS == 4.0 and covers.PACER.interval == 4.0
    assert covers.DEFAULT_BATCH <= 3 and covers.MAX_BATCH <= 5


def test_requests_are_paced_across_batches_not_just_within_one(client, monkeypatch, sleeps):
    pace = covers.REQUEST_INTERVAL_SECONDS
    for number in range(4):
        make_book(client, f"Book {number}", isbn_13=isbn13(10 + number))
    script = Script()
    monkeypatch.setattr(covers, "lookup_cover", script)
    enrich(client, limit=2)
    assert sleeps == [pace]  # nothing before the first request, then a full gap
    enrich(client, limit=2, skip=[])  # a second batch continues the same pace
    assert sleeps[:2] == [pace, pace] and len(script.calls) == 4


def test_concurrent_callers_cannot_bypass_the_pacer():
    clock = {"t": 0.0}
    slept: list[float] = []

    def sleep(seconds):
        slept.append(seconds)
        clock["t"] += seconds

    pacer = covers.Pacer(4.0, clock=lambda: clock["t"], sleep=sleep)

    def one_lookup():
        pacer.wait()
        pacer.finished()

    workers = [threading.Thread(target=one_lookup) for _ in range(3)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    assert sorted(slept) == [4.0, 4.0]  # every caller after the first waited a full interval


def test_pacer_waits_only_for_the_time_remaining():
    now = {"t": 100.0}
    slept: list[float] = []
    pacer = covers.Pacer(2.0, clock=lambda: now["t"], sleep=slept.append)
    pacer.wait()
    now["t"] += 0.5
    pacer.wait()
    now["t"] += 5
    pacer.wait()
    assert slept == [pytest.approx(1.5)]


# ------------------------------------------------------------------ rate limiting


def test_a_429_stops_the_batch_immediately_and_starts_a_cooldown(
    client, monkeypatch, sleeps, clock
):
    for number in range(6):
        make_book(client, f"Book {number}", isbn_13=isbn13(20 + number))
    script = Script({isbn13(21): covers.Lookup(covers.RATE_LIMITED, 120.0)})
    monkeypatch.setattr(covers, "lookup_cover", script)
    result = enrich(client, limit=5)
    assert result["rate_limited"] and result["stopped_early"]
    assert script.calls == [isbn13(20), isbn13(21)]  # stopped at the 429, no retries
    assert result["found"] == 0 and result["not_found"] == 1
    assert result["retry_after_seconds"] == 120 and result["blocked_until"] is not None
    assert len(sleeps) == 1  # paced, never a tight loop

    again = enrich(client)  # still cooling down
    assert script.calls == [isbn13(20), isbn13(21)]  # no request was made
    assert again["rate_limited"] and again["checked"] == 0
    assert again["retry_after_seconds"] == 120
    clock["now"] += timedelta(seconds=60)
    assert enrich(client)["retry_after_seconds"] == 60  # counts down
    status = client.get("/api/books/covers/missing").json()
    assert status["retry_after_seconds"] == 60 and status["blocked_until"] is not None
    assert len(script.calls) == 2

    clock["now"] += timedelta(seconds=61)  # cooldown over
    script.outcomes[isbn13(21)] = covers.NOT_FOUND  # Open Library has calmed down
    resumed = enrich(client, limit=2)
    assert not resumed["rate_limited"] and resumed["retry_after_seconds"] is None
    assert len(script.calls) == 4
    assert client.get("/api/books/covers/missing").json()["blocked_until"] is None


def test_the_cooldown_survives_a_backend_restart(client, application, monkeypatch, sleeps, clock):
    make_book(client, "Only", isbn_13=isbn13(30))
    monkeypatch.setattr(
        covers, "lookup_cover", Script({isbn13(30): covers.Lookup(covers.RATE_LIMITED, 600.0)})
    )
    assert enrich(client)["rate_limited"]
    with application.state.session_factory() as db:
        state = db.get(CoverServiceState, covers.SERVICE)
        assert state.blocked_until == clock["now"] + timedelta(seconds=600)
    after = Script()
    monkeypatch.setattr(covers, "lookup_cover", after)
    with TestClient(create_app(application.state.settings)) as restarted:
        result = enrich(restarted)
        assert result["rate_limited"] and result["checked"] == 0 and after.calls == []
        assert result["retry_after_seconds"] == 600


@pytest.mark.parametrize(
    "retry_after,expected",
    [
        (None, covers.DEFAULT_COOLDOWN_SECONDS),  # no header: a cautious default
        (0.0, covers.MIN_COOLDOWN_SECONDS),  # never "retry right now"
        (5.0, covers.MIN_COOLDOWN_SECONDS),
        (90.0, 90),
        (10**9, covers.MAX_COOLDOWN_SECONDS),  # absurd values are capped
    ],
)
def test_cooldown_length_is_bounded_and_defaults_sensibly(
    client, monkeypatch, sleeps, clock, retry_after, expected
):
    make_book(client, "Only", isbn_13=isbn13(31))
    monkeypatch.setattr(
        covers,
        "lookup_cover",
        Script({isbn13(31): covers.Lookup(covers.RATE_LIMITED, retry_after)}),
    )
    assert enrich(client)["retry_after_seconds"] == expected


def test_retry_after_in_both_formats_flows_through_a_real_lookup(
    client, monkeypatch, sleeps, clock
):
    make_book(client, "Only", isbn_13=isbn13(32))
    seen = []

    def fake_urlopen(request, timeout=None):
        seen.append(request.get_method())
        raise http_error(429, "75")

    monkeypatch.setattr(covers.urllib.request, "urlopen", fake_urlopen)
    assert enrich(client)["retry_after_seconds"] == 75 and seen == ["HEAD"]
    clock["now"] += timedelta(seconds=76)
    date = email.utils.format_datetime(clock["now"] + timedelta(seconds=200), usegmt=True)
    monkeypatch.setattr(
        covers.urllib.request,
        "urlopen",
        lambda r, timeout=None: (_ for _ in ()).throw(http_error(503, date)),
    )
    assert 195 <= enrich(client)["retry_after_seconds"] <= 200


# ------------------------------------------------------------------ the persisted cache


def test_lookups_are_cached_with_a_timestamp_and_never_repeated(
    client, application, monkeypatch, sleeps, clock
):
    hit = make_book(client, "Has cover", isbn_13=isbn13(40))
    miss = make_book(client, "No cover", isbn_13=isbn13(41))
    script = Script({isbn13(40): covers.FOUND})
    monkeypatch.setattr(covers, "lookup_cover", script)
    first = enrich(client)
    assert first["found"] == 1 and first["not_found"] == 1 and first["checked"] == 2
    with application.state.session_factory() as db:
        rows = {row.isbn: row for row in db.scalars(select(CoverLookup))}
        assert {k: v.result for k, v in rows.items()} == {
            isbn13(40): "found",
            isbn13(41): "not_found",
        }
        assert all(row.looked_up_at == clock["now"] for row in rows.values())

    # the "no cover" answer is remembered: nothing is asked again and it is no longer "missing"
    assert enrich(client)["checked"] == 0 and len(script.calls) == 2
    assert client.get("/api/books/covers/missing").json()["count"] == 0
    # clearing a cover by hand and re-running restores it from the cache, without a request
    assert (
        client.patch(f"/api/books/{hit['id']}", json={"cover_url": ""}).json()["cover_url"] is None
    )
    assert client.get("/api/books/covers/missing").json()["count"] == 1
    again = enrich(client)
    assert again["cached"] == 1 and again["checked"] == 0 and again["found"] == 1
    assert len(script.calls) == 2
    assert client.get(f"/api/books/{hit['id']}").json()["cover_url"].endswith(f"{isbn13(40)}-M.jpg")
    assert client.get(f"/api/books/{miss['id']}").json()["cover_url"] is None


def test_the_cache_survives_restarts(client, application, monkeypatch, sleeps, clock):
    make_book(client, "Cached", isbn_13=isbn13(42))
    make_book(client, "Cached miss", isbn_13=isbn13(43))
    monkeypatch.setattr(covers, "lookup_cover", Script({isbn13(42): covers.FOUND}))
    enrich(client)
    quiet = Script()
    monkeypatch.setattr(covers, "lookup_cover", quiet)
    with TestClient(create_app(application.state.settings)) as restarted:
        assert restarted.get("/api/books/covers/missing").json()["count"] == 0
        assert enrich(restarted)["checked"] == 0
    assert quiet.calls == []


def test_a_no_cover_answer_is_rechecked_after_it_goes_stale(client, monkeypatch, sleeps, clock):
    make_book(client, "Maybe later", isbn_13=isbn13(44))
    script = Script()
    monkeypatch.setattr(covers, "lookup_cover", script)
    enrich(client)
    clock["now"] += covers.NOT_FOUND_TTL - timedelta(days=1)
    assert enrich(client)["checked"] == 0 and len(script.calls) == 1
    clock["now"] += timedelta(days=2)
    assert client.get("/api/books/covers/missing").json()["count"] == 1
    script.outcomes[isbn13(44)] = covers.FOUND
    assert enrich(client)["found"] == 1 and len(script.calls) == 2


def test_errors_and_rate_limits_are_never_cached(client, application, monkeypatch, sleeps, clock):
    make_book(client, "Flaky", isbn_13=isbn13(45))
    make_book(client, "Limited", isbn_13=isbn13(46))
    monkeypatch.setattr(covers, "lookup_cover", Script({isbn13(45): covers.ERROR}))
    assert enrich(client)["errors"] == 1
    with application.state.session_factory() as db:
        assert db.get(CoverLookup, isbn13(45)) is None  # an error is not an answer
    clock["now"] += timedelta(seconds=1)
    monkeypatch.setattr(
        covers, "lookup_cover", Script({isbn13(45): covers.Lookup(covers.RATE_LIMITED, 30.0)})
    )
    assert enrich(client)["rate_limited"]
    with application.state.session_factory() as db:
        assert db.get(CoverLookup, isbn13(45)) is None  # nor is a 429
    clock["now"] += timedelta(seconds=31)
    script = Script({isbn13(45): covers.FOUND})
    monkeypatch.setattr(covers, "lookup_cover", script)
    assert enrich(client, limit=1)["found"] == 1 and script.calls == [isbn13(45)]  # asked afresh


def test_books_sharing_an_isbn_cost_one_request(client, monkeypatch, sleeps, clock):
    for title in ("Twin A", "Twin B", "Twin C"):
        make_book(client, title, isbn_13=isbn13(47))
    script = Script({isbn13(47): covers.FOUND})
    monkeypatch.setattr(covers, "lookup_cover", script)
    result = enrich(client, limit=5)
    assert script.calls == [isbn13(47)] and result["found"] == 3 and result["checked"] == 1


# ------------------------------------------------------------------ no write lock during requests


@pytest.mark.skipif(bool(os.getenv("TEST_DATABASE_URL")), reason="SQLite-specific locking check")
def test_no_database_write_lock_is_held_while_waiting_on_the_network(
    client, application, monkeypatch, sleeps, clock
):
    for number in range(3):
        make_book(client, f"Book {number}", isbn_13=isbn13(50 + number))
    path = application.state.engine.url.database
    attempts: list[str] = []

    def lookup(isbn):
        other = sqlite3.connect(path, timeout=0.3)  # a second, independent writer
        try:
            other.execute("BEGIN IMMEDIATE")  # fails with "database is locked" if held
            other.execute("ROLLBACK")
            attempts.append("writable")
        except sqlite3.OperationalError as exc:
            attempts.append(f"blocked: {exc}")
        finally:
            other.close()
        return covers.Lookup(covers.FOUND if isbn == isbn13(50) else covers.NOT_FOUND)

    monkeypatch.setattr(covers, "lookup_cover", lookup)
    result = enrich(client, limit=3)
    assert result["checked"] == 3
    assert attempts == ["writable"] * 3, attempts


# ------------------------------------------------------------------ preservation


def book_snapshot(db):
    skip = {"cover_url", "updated_at"}
    return {
        book.id: {
            c.name: getattr(book, c.name) for c in Book.__table__.columns if c.name not in skip
        }
        for book in db.scalars(select(Book))
    }


def test_enrichment_changes_only_empty_cover_fields(
    client, application, monkeypatch, sleeps, clock
):
    manual = make_book(
        client,
        "Hand picked",
        authors=["A. Author"],
        isbn_13=isbn13(60),
        publisher="My Press",
        description="Mine",
        publication_year=1999,
        edition="2nd",
        goodreads_id="G60",
        cover_url="https://example.com/mine.jpg",
    )
    needs = make_book(client, "Needs one", authors=["B"], isbn_13=isbn13(61), publisher="P")
    note = client.post(
        "/api/notes", json={"title": "Quote", "book_id": manual["id"], "content": "x"}
    ).json()
    other = client.post("/api/notes", json={"title": "Reflection", "book_id": needs["id"]}).json()
    link = client.post(
        f"/api/notes/{note['id']}/connections",
        json={"target_note_id": other["id"], "link_type": "develops", "explanation": "because"},
    ).json()
    foreign_user = uuid4()
    with application.state.session_factory.begin() as db:
        db.add(User(id=foreign_user, timezone="UTC"))
        db.flush()
        db.add(Book(user_id=foreign_user, title="Theirs", authors=[], isbn_13=isbn13(62)))
    with application.state.session_factory() as db:
        before = book_snapshot(db)
        counts_before = (
            db.scalar(select(func.count()).select_from(Book)),
            db.scalar(select(func.count()).select_from(Note)),
            db.scalar(select(func.count()).select_from(NoteLink)),
        )
    monkeypatch.setattr(covers, "lookup_cover", Script(default=covers.FOUND))
    result = enrich(client, limit=5)
    assert [u["id"] for u in result["updated"]] == [
        needs["id"]
    ]  # the manual cover was never a candidate

    with application.state.session_factory() as db:
        assert book_snapshot(db) == before  # every other field is identical
        assert (
            db.scalar(select(func.count()).select_from(Book)),
            db.scalar(select(func.count()).select_from(Note)),
            db.scalar(select(func.count()).select_from(NoteLink)),
        ) == counts_before
        assert db.scalar(select(Book.cover_url).where(Book.user_id == foreign_user)) is None
    assert (
        client.get(f"/api/books/{manual['id']}").json()["cover_url"]
        == "https://example.com/mine.jpg"
    )
    assert client.get(f"/api/notes/{note['id']}").json()["content"] == "x"
    assert [c["id"] for c in client.get(f"/api/notes/{note['id']}/connections").json()] == [
        link["id"]
    ]
    assert client.get(f"/api/books/{needs['id']}").json()["note_count"] == 1


def test_a_cached_cover_never_replaces_a_manually_entered_one(client, monkeypatch, sleeps, clock):
    book = make_book(client, "Mine", isbn_13=isbn13(63))
    script = Script({isbn13(63): covers.FOUND})
    monkeypatch.setattr(covers, "lookup_cover", script)
    enrich(client)
    client.patch(f"/api/books/{book['id']}", json={"cover_url": "https://example.com/manual.jpg"})
    assert enrich(client)["checked"] == 0
    assert (
        client.get(f"/api/books/{book['id']}").json()["cover_url"]
        == "https://example.com/manual.jpg"
    )
    assert script.calls == [isbn13(63)]


def test_enrichment_is_opt_in_bounded_and_cancellable(client, monkeypatch, sleeps, clock):
    for number in range(8):
        make_book(client, f"Book {number}", isbn_13=isbn13(70 + number))
    script = Script()
    monkeypatch.setattr(covers, "lookup_cover", script)
    assert script.calls == []  # nothing runs on its own
    assert client.post("/api/books/covers/enrich", json={"limit": 6}).status_code == 422
    assert client.post("/api/books/covers/enrich", json={"limit": 0}).status_code == 422
    first = enrich(client, limit=5)
    assert len(script.calls) == 5 == first["checked"]  # a batch is bounded
    # "cancel" is simply not calling again: nothing further happens and what was learned is kept
    assert len(script.calls) == 5
    assert enrich(client, limit=5)["checked"] == 3 and len(script.calls) == 8


# ------------------------------------------------------------------ cover IDs


def test_cover_ids_are_extracted_only_when_unmistakable():
    direct = "https://covers.openlibrary.org/b/id/8231856-L.jpg"
    archive = (
        "https://ia800506.us.archive.org/zipview.php"
        "?zip=/5/items/olcovers823/olcovers823-L.zip&file=8231856-L.jpg"
    )
    assert covers.extract_cover_id(direct) == 8231856
    assert covers.extract_cover_id(archive) == 8231856
    assert covers.extract_cover_id("https://covers.openlibrary.org/b/id/123-M.jpg?x=1") == 123
    for url in (
        None,
        "",
        "https://covers.openlibrary.org/b/isbn/9780000000002-L.jpg",  # not an ID form
        "https://covers.openlibrary.org/b/id/0-L.jpg",  # zero is not a cover
        "https://covers.openlibrary.org/b/id/abc-L.jpg",
        "https://example.com/8231856-L.jpg",  # digits alone prove nothing
    ):
        assert covers.extract_cover_id(url) is None, url


def test_lookup_reads_the_cover_id_from_the_final_redirected_url(monkeypatch):
    class Response:
        status = 200
        url = "https://covers.openlibrary.org/b/id/424242-L.jpg"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(covers.urllib.request, "urlopen", lambda r, timeout=None: Response())
    assert covers.lookup_cover(isbn13(92)) == covers.Lookup(covers.FOUND, cover_id=424242)


def test_a_found_cover_stores_the_id_based_url(client, application, monkeypatch, sleeps, clock):
    book = make_book(client, "With id", isbn_13=isbn13(90))
    monkeypatch.setattr(
        covers,
        "lookup_cover",
        Script({isbn13(90): covers.Lookup(covers.FOUND, cover_id=8231856)}),
    )
    assert enrich(client)["found"] == 1
    url = client.get(f"/api/books/{book['id']}").json()["cover_url"]
    assert url == "https://covers.openlibrary.org/b/id/8231856-M.jpg"
    with application.state.session_factory() as db:
        row = db.get(CoverLookup, isbn13(90))
        assert row.result == "found" and row.cover_id == 8231856


def test_without_a_verified_id_the_isbn_url_is_still_used(client, monkeypatch, sleeps, clock):
    book = make_book(client, "No id", isbn_13=isbn13(91))
    monkeypatch.setattr(covers, "lookup_cover", Script({isbn13(91): covers.FOUND}))
    enrich(client)
    url = client.get(f"/api/books/{book['id']}").json()["cover_url"]
    assert url == f"https://covers.openlibrary.org/b/isbn/{isbn13(91)}-M.jpg"


def test_a_cached_cover_id_is_applied_without_any_request(
    client, application, monkeypatch, sleeps, clock
):
    book = make_book(client, "Cached id", isbn_13=isbn13(93))
    with application.state.session_factory.begin() as db:
        db.add(
            CoverLookup(isbn=isbn13(93), result="found", cover_id=777, looked_up_at=clock["now"])
        )
    quiet = Script()
    monkeypatch.setattr(covers, "lookup_cover", quiet)
    result = enrich(client)
    assert result["cached"] == 1 and result["found"] == 1 and quiet.calls == []
    url = client.get(f"/api/books/{book['id']}").json()["cover_url"]
    assert url == "https://covers.openlibrary.org/b/id/777-M.jpg"


# ------------------------------------------------------------------ legacy ISBN-hotlinked covers


def legacy_url(isbn):
    return f"https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg"


def test_legacy_isbn_covers_convert_gradually_within_the_batch_budget(
    client, monkeypatch, sleeps, clock
):
    books = [
        make_book(
            client, f"Old {n}", isbn_13=isbn13(100 + n), cover_url=legacy_url(isbn13(100 + n))
        )
        for n in range(3)
    ]
    script = Script(
        {isbn13(100 + n): covers.Lookup(covers.FOUND, cover_id=5000 + n) for n in range(3)}
    )
    monkeypatch.setattr(covers, "lookup_cover", script)
    first = enrich(client, limit=2)  # a budget of two requests converts two covers
    assert first["converted"] == 2 and first["checked"] == 2 and first["found"] == 0
    assert first["legacy_remaining"] == 1
    assert {u["cover_url"] for u in first["updated"]} == {
        "https://covers.openlibrary.org/b/id/5000-M.jpg",
        "https://covers.openlibrary.org/b/id/5001-M.jpg",
    }
    second = enrich(client, limit=2, skip=first["checked_ids"])
    assert second["converted"] == 1 and len(script.calls) == 3
    done = enrich(client, limit=2)
    assert done["checked"] == 0 and done["converted"] == 0  # nothing legacy remains
    assert done["legacy_remaining"] == 0
    for n, book in enumerate(books):
        url = client.get(f"/api/books/{book['id']}").json()["cover_url"]
        assert url == f"https://covers.openlibrary.org/b/id/{5000 + n}-M.jpg"


def test_a_legacy_cover_is_never_replaced_without_a_verified_id(
    client, monkeypatch, sleeps, clock
):
    no_id = make_book(client, "A keeps", isbn_13=isbn13(110), cover_url=legacy_url(isbn13(110)))
    gone = make_book(client, "B keeps", isbn_13=isbn13(111), cover_url=legacy_url(isbn13(111)))
    script = Script({isbn13(110): covers.FOUND, isbn13(111): covers.NOT_FOUND})
    monkeypatch.setattr(covers, "lookup_cover", script)
    assert enrich(client, limit=5)["converted"] == 0
    assert client.get(f"/api/books/{no_id['id']}").json()["cover_url"] == legacy_url(isbn13(110))
    assert client.get(f"/api/books/{gone['id']}").json()["cover_url"] == legacy_url(isbn13(111))
    # both answers were remembered, so neither is asked again
    assert enrich(client, limit=5)["checked"] == 0 and len(script.calls) == 2


def test_a_legacy_conversion_error_leaves_the_cover_alone(client, monkeypatch, sleeps, clock):
    book = make_book(client, "Flaky old", isbn_13=isbn13(112), cover_url=legacy_url(isbn13(112)))
    monkeypatch.setattr(covers, "lookup_cover", Script({isbn13(112): covers.ERROR}))
    result = enrich(client)
    assert result["errors"] == 1 and result["converted"] == 0
    assert client.get(f"/api/books/{book['id']}").json()["cover_url"] == legacy_url(isbn13(112))


def test_a_429_during_conversion_starts_the_same_cooldown(client, monkeypatch, sleeps, clock):
    make_book(client, "Old limited", isbn_13=isbn13(113), cover_url=legacy_url(isbn13(113)))
    script = Script({isbn13(113): covers.Lookup(covers.RATE_LIMITED, 120.0)})
    monkeypatch.setattr(covers, "lookup_cover", script)
    result = enrich(client)
    assert result["rate_limited"] and result["retry_after_seconds"] == 120
    assert enrich(client)["rate_limited"] and len(script.calls) == 1  # cooldown honoured


# ------------------------------------------------------------------ progress reporting


def test_the_missing_covers_status_reports_progress(client, monkeypatch, sleeps, clock):
    make_book(client, "Has", isbn_13=isbn13(120))
    make_book(client, "Hasn't", isbn_13=isbn13(121))
    make_book(client, "Manual", cover_url="https://example.com/x.jpg")
    monkeypatch.setattr(
        covers, "lookup_cover", Script({isbn13(120): covers.Lookup(covers.FOUND, cover_id=9)})
    )
    enrich(client)
    status = client.get("/api/books/covers/missing").json()
    assert status == {
        "count": 0,
        "with_covers": 2,
        "found_lookups": 1,
        "not_found_lookups": 1,
        "blocked_until": None,
        "retry_after_seconds": None,
        "cooldown_reason": None,
    }


def test_migration_0007_adds_the_cover_id_column_and_keeps_data(application):
    from pathlib import Path

    import sqlalchemy as sa
    from alembic import command
    from alembic.config import Config

    with application.state.session_factory.begin() as db:
        db.add(CoverLookup(isbn=isbn13(81), result="not_found", looked_up_at=datetime.now(UTC)))
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with application.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0006")
        columns = {c["name"] for c in sa.inspect(connection).get_columns("cover_lookups")}
        assert "cover_id" not in columns
        assert connection.scalar(sa.text("SELECT result FROM cover_lookups")) == "not_found"
        command.upgrade(config, "head")
        columns = {c["name"] for c in sa.inspect(connection).get_columns("cover_lookups")}
        assert "cover_id" in columns
        assert connection.scalar(sa.text("SELECT cover_id FROM cover_lookups")) is None


# ------------------------------------------------------------------ diagnostics logging


@pytest.mark.parametrize("code", [429, 503])
def test_rate_limit_responses_are_logged_with_status_and_header(monkeypatch, caplog, code):
    import logging

    monkeypatch.setattr(
        covers.urllib.request,
        "urlopen",
        lambda r, timeout=None: (_ for _ in ()).throw(http_error(code, "120")),
    )
    with caplog.at_level(logging.WARNING, logger="app.services.covers"):
        result = covers.lookup_cover(isbn13(1))
    assert result.http_status == code
    assert f"http_status={code}" in caplog.text and "retry_after_header='120'" in caplog.text
    assert isbn13(1) not in caplog.text  # no identifiers in the log


def test_the_cooldown_start_is_logged_with_operation_and_sequence(
    client, monkeypatch, sleeps, clock, caplog
):
    import logging

    make_book(client, "First", isbn_13=isbn13(33))
    make_book(client, "Second", isbn_13=isbn13(34))
    monkeypatch.setattr(
        covers,
        "lookup_cover",
        Script(
            {isbn13(34): covers.Lookup(covers.RATE_LIMITED, 60.0, http_status=429)},
        ),
    )
    with caplog.at_level(logging.INFO, logger="app.services.covers"):
        assert enrich(client, limit=5)["rate_limited"]
    assert "open_library lookup: op=enrich request=1 result=not_found" in caplog.text
    assert "op=enrich request=2 reason=rate_limited http_status=429 retry_after=60.0" in caplog.text
    assert "cooldown started" in caplog.text and "blocked_until=" in caplog.text
    assert isbn13(33) not in caplog.text and isbn13(34) not in caplog.text


def test_a_cooldown_during_legacy_conversion_is_logged_as_such(
    client, monkeypatch, sleeps, clock, caplog
):
    import logging

    make_book(client, "Old", isbn_13=isbn13(35), cover_url=legacy_url(isbn13(35)))
    monkeypatch.setattr(
        covers,
        "lookup_cover",
        Script({isbn13(35): covers.Lookup(covers.UNAVAILABLE, None, http_status=503)}),
    )
    with caplog.at_level(logging.INFO, logger="app.services.covers"):
        assert enrich(client)["unavailable"]
    assert (
        "op=convert_legacy request=1 reason=unavailable http_status=503 retry_after=None"
        in caplog.text
    )


# ------------------------------------------------------------------ 503: temporarily unavailable


def test_a_503_without_retry_after_pauses_briefly_not_fifteen_minutes(
    client, monkeypatch, sleeps, clock
):
    make_book(client, "Only", isbn_13=isbn13(130))
    script = Script({isbn13(130): covers.Lookup(covers.UNAVAILABLE, None, http_status=503)})
    monkeypatch.setattr(covers, "lookup_cover", script)
    result = enrich(client)
    assert result["unavailable"] and not result["rate_limited"] and result["stopped_early"]
    assert result["cooldown_reason"] == "unavailable"
    assert result["retry_after_seconds"] == covers.UNAVAILABLE_COOLDOWN_SECONDS == 60
    # the pause is honoured without any further request, and keeps its reason
    again = enrich(client)
    assert again["unavailable"] and not again["rate_limited"] and len(script.calls) == 1
    status = client.get("/api/books/covers/missing").json()
    assert status["cooldown_reason"] == "unavailable" and status["retry_after_seconds"] == 60
    # once it passes, lookups resume: the failure cached nothing
    clock["now"] += timedelta(seconds=61)
    script.outcomes[isbn13(130)] = covers.NOT_FOUND
    resumed = enrich(client)
    assert not resumed["unavailable"] and not resumed["rate_limited"]
    assert len(script.calls) == 2 and resumed["cooldown_reason"] is None


def test_a_503_with_retry_after_is_honoured_conservatively(client, monkeypatch, sleeps, clock):
    make_book(client, "Only", isbn_13=isbn13(131))
    monkeypatch.setattr(
        covers,
        "lookup_cover",
        Script({isbn13(131): covers.Lookup(covers.UNAVAILABLE, 300.0, http_status=503)}),
    )
    result = enrich(client)
    assert result["cooldown_reason"] == "unavailable"
    assert result["retry_after_seconds"] == 300  # the header wins over the short default


def test_a_real_503_is_classified_as_unavailable_and_never_cached(
    client, application, monkeypatch, sleeps, clock
):
    make_book(client, "Only", isbn_13=isbn13(132))
    monkeypatch.setattr(
        covers.urllib.request,
        "urlopen",
        lambda r, timeout=None: (_ for _ in ()).throw(http_error(503)),
    )
    result = enrich(client)
    assert result["unavailable"] and not result["rate_limited"]
    assert result["checked"] == 1  # the batch stopped at once, no retry
    with application.state.session_factory() as db:
        assert db.get(CoverLookup, isbn13(132)) is None  # a 503 is not an answer


def test_a_real_429_still_gets_the_cautious_rate_limit_default(
    client, monkeypatch, sleeps, clock
):
    make_book(client, "Only", isbn_13=isbn13(133))
    monkeypatch.setattr(
        covers.urllib.request,
        "urlopen",
        lambda r, timeout=None: (_ for _ in ()).throw(http_error(429)),
    )
    result = enrich(client)
    assert result["rate_limited"] and not result["unavailable"]
    assert result["cooldown_reason"] == "rate_limited"
    assert result["retry_after_seconds"] == covers.DEFAULT_COOLDOWN_SECONDS


def test_migration_0006_adds_tables_and_keeps_existing_data(application):
    from pathlib import Path

    import sqlalchemy as sa
    from alembic import command
    from alembic.config import Config

    with application.state.session_factory.begin() as db:
        user = User(id=uuid4(), timezone="UTC")
        db.add(user)
        db.flush()
        db.add(
            Book(
                user_id=user.id,
                title="Existing",
                authors=["A"],
                isbn_13=isbn13(80),
                cover_url="https://example.com/keep.jpg",
            )
        )
        db.add(CoverLookup(isbn=isbn13(80), result="found", looked_up_at=datetime.now(UTC)))
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with application.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0005")
        tables = set(sa.inspect(connection).get_table_names())
        assert not tables & {"cover_lookups", "cover_service_state"}
        assert connection.scalar(sa.text("SELECT title FROM books")) == "Existing"
        assert (
            connection.scalar(sa.text("SELECT cover_url FROM books"))
            == "https://example.com/keep.jpg"
        )
        command.upgrade(config, "head")
        assert {"cover_lookups", "cover_service_state"} <= set(
            sa.inspect(connection).get_table_names()
        )
        assert connection.scalar(sa.text("SELECT title FROM books")) == "Existing"
