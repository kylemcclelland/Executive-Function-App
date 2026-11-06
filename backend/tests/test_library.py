from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.main import create_app
from app.models import Book, Note, NoteLink, Project, User


def book(client, title="Summa Theologiae", **kwargs):
    response = client.post("/api/books", json={"title": title, **kwargs})
    assert response.status_code == 201, response.text
    return response.json()


def note(client, title="A note", **kwargs):
    response = client.post("/api/notes", json={"title": title, **kwargs})
    assert response.status_code == 201, response.text
    return response.json()


def connect(client, source, target, link_type="related_to", **kwargs):
    return client.post(
        f"/api/notes/{source['id']}/connections",
        json={
            "target_note_id": target["id"],
            "link_type": link_type,
            **kwargs,
        },
    )


# ---------------------------------------------------------------- books


def test_book_crud_with_every_field(client):
    created = book(
        client,
        "  Summa Theologiae  ",
        authors=["Thomas Aquinas", " Thomas Aquinas ", ""],
        isbn_10="0-87061-212-5",
        isbn_13="978-0-87061-212-9",
        publication_year=1274,
        publisher="Christian Classics",
        edition="Vol. 1",
        goodreads_id="12345",
        cover_url="https://example.com/cover.jpg",
        description="  The great synthesis.  ",
    )
    assert created["title"] == "Summa Theologiae"
    assert created["authors"] == ["Thomas Aquinas"]
    assert created["isbn_10"] == "0870612125" and created["isbn_13"] == "9780870612129"
    assert created["note_count"] == 0 and created["created_at"].endswith("Z")
    path = f"/api/books/{created['id']}"
    assert client.get(path).json() == created
    edited = client.patch(
        path,
        json={
            "title": "Summa",
            "authors": ["Aquinas", "Pegis"],
            "publisher": "  ",
            "cover_url": "",
            "publication_year": None,
            "edition": "Vol. 2",
        },
    ).json()
    assert edited["title"] == "Summa" and edited["authors"] == ["Aquinas", "Pegis"]
    assert edited["publisher"] is None and edited["cover_url"] is None
    assert edited["publication_year"] is None and edited["edition"] == "Vol. 2"
    assert edited["isbn_13"] == "9780870612129"  # untouched fields survive
    assert edited["updated_at"] >= created["updated_at"]
    assert client.delete(path).status_code == 204
    assert client.get(path).status_code == 404


def test_a_book_needs_only_a_title(client):
    created = book(client, "Untitled")
    assert created["authors"] == [] and created["isbn_10"] is None
    assert created["publication_year"] is None and created["description"] is None


@pytest.mark.parametrize(
    "payload",
    [
        {"title": ""},
        {"title": "   "},
        {"title": "x", "isbn_10": "123"},
        {"title": "x", "isbn_13": "12345"},
        {"title": "x", "isbn_10": "12345678901"},
        {"title": "x", "isbn_13": "97808706121AB"},
        {"title": "x", "cover_url": "javascript:alert(1)"},
        {"title": "x", "cover_url": "ftp://x.test/a.png"},
        {"title": "x", "cover_url": "not a url"},
        {"title": "x", "publication_year": 5000},
        {"title": "x", "goodreads_id": "has spaces"},
        {"title": "x", "authors": [f"Author {i}" for i in range(21)]},
        {"title": "x", "user_id": str(uuid4())},
        {"title": "x" * 301},
    ],
)
def test_book_validation(client, payload):
    assert client.post("/api/books", json=payload).status_code == 422


def test_isbn_10_may_end_in_x_and_null_required_fields_are_rejected(client):
    created = book(client, "Classic", isbn_10="080442957x")
    assert created["isbn_10"] == "080442957X"
    for field in ("title", "authors"):
        assert client.patch(f"/api/books/{created['id']}", json={field: None}).status_code == 422


def test_book_has_no_reading_status_progress_or_rating_fields(client):
    keys = set(book(client))
    assert not keys & {"status", "progress", "rating", "shelf", "finished", "percent_read"}
    for field in ("status", "rating", "progress"):
        assert client.post("/api/books", json={"title": "x", field: 1}).status_code == 422


def test_goodreads_id_must_be_unique_per_user(client):
    first = book(client, "One", goodreads_id="42")
    assert client.post("/api/books", json={"title": "Dup", "goodreads_id": "42"}).status_code == 409
    other = book(client, "Two", goodreads_id="43")
    assert client.patch(f"/api/books/{other['id']}", json={"goodreads_id": "42"}).status_code == 409
    assert client.patch(f"/api/books/{first['id']}", json={"goodreads_id": "42"}).status_code == 200
    book(client, "No id")
    book(client, "Also no id")  # many books may omit it


def test_book_search_and_note_counts(client):
    summa = book(
        client, "Summa Theologiae", authors=["Thomas Aquinas"], publisher="Ave Maria Press"
    )
    book(client, "Confessions", authors=["Augustine of Hippo"], isbn_13="9780140449655")
    book(client, "The 50% Rule_")
    note(client, "A", book_id=summa["id"])
    note(client, "B", book_id=summa["id"])

    def titles(query):
        return [item["title"] for item in client.get(f"/api/books?q={query}").json()]

    assert titles("") == ["Confessions", "Summa Theologiae", "The 50% Rule_"]
    assert titles("aquinas") == ["Summa Theologiae"]
    assert titles("AUGUSTINE") == ["Confessions"]
    assert titles("ave maria") == ["Summa Theologiae"]
    assert titles("9780140449655") == ["Confessions"]
    assert titles("%25") == ["The 50% Rule_"]  # LIKE wildcards are escaped
    assert titles("_") == ["The 50% Rule_"]
    assert titles("nothing") == []
    counts = {item["title"]: item["note_count"] for item in client.get("/api/books").json()}
    assert counts == {"Confessions": 0, "Summa Theologiae": 2, "The 50% Rule_": 0}


# ---------------------------------------------------------------- notes


def test_note_crud_and_types(client):
    created = note(
        client,
        "  On beatitude  ",
        content="# Heading\n\nline one\nline two",
        note_type="quotation",
        source_location="ST I–II, q. 1, a. 8",
        tags=["Ethics", " #Telos ", "ethics"],
    )
    assert created["title"] == "On beatitude"
    assert created["content"] == "# Heading\n\nline one\nline two"  # stored verbatim
    assert (
        created["note_type"] == "quotation" and created["source_location"] == "ST I–II, q. 1, a. 8"
    )
    assert created["tags"] == ["ethics", "telos"]
    assert created["book_id"] is None and created["project_id"] is None
    assert created["created_at"].endswith("Z") and created["excerpt"].startswith("# Heading")
    path = f"/api/notes/{created['id']}"
    assert client.get(path).json() == created
    edited = client.patch(
        path,
        json={
            "title": "On the last end",
            "content": "Updated",
            "note_type": "reflection",
            "source_location": " ",
            "tags": ["telos", "happiness"],
        },
    ).json()
    assert edited["title"] == "On the last end" and edited["note_type"] == "reflection"
    assert edited["source_location"] is None and edited["tags"] == ["happiness", "telos"]
    assert edited["id"] == created["id"] and edited["updated_at"] >= created["updated_at"]
    assert client.patch(path, json={"tags": []}).json()["tags"] == []
    assert client.delete(path).status_code == 204
    assert client.get(path).status_code == 404


def test_a_note_is_independent_by_default_and_every_type_is_accepted(client):
    plain = note(client)
    assert plain["note_type"] == "general" and plain["content"] == ""
    for note_type in ("general", "reading_note", "quotation", "reflection", "research", "question"):
        assert note(client, note_type, note_type=note_type)["note_type"] == note_type


@pytest.mark.parametrize(
    "payload",
    [
        {"title": ""},
        {"title": "   "},
        {"title": "x", "note_type": "summary"},
        {"title": "x", "content": "x" * 200001},
        {"title": "x", "source_location": "x" * 301},
        {"title": "x", "book_id": str(uuid4())},
        {"title": "x", "project_id": str(uuid4())},
        {"title": "x", "user_id": str(uuid4())},
    ],
)
def test_note_validation_and_unknown_references(client, payload):
    assert client.post("/api/notes", json=payload).status_code in (404, 422)
    assert client.get("/api/notes").json() == []


def test_null_required_note_fields_are_rejected(client):
    created = note(client)
    for field in ("title", "content", "note_type", "tags"):
        assert client.patch(f"/api/notes/{created['id']}", json={field: None}).status_code == 422


def test_long_notes_round_trip_without_loss(client):
    body = ("Paragraph one.\n\n" + "A long line of argument. " * 40 + "\n") * 100
    created = note(client, "Long", content=body)
    assert len(body) > 50000
    assert client.get(f"/api/notes/{created['id']}").json()["content"] == body


def test_markdown_and_html_are_stored_verbatim_never_executed_server_side(client):
    hostile = "<script>alert(1)</script> [x](javascript:alert(1)) ![i](http://t.example/p.png)"
    created = note(client, "Hostile", content=hostile)
    assert client.get(f"/api/notes/{created['id']}").json()["content"] == hostile


def test_book_and_project_associations(client):
    summa = book(client)
    other_book = book(client, "Confessions")
    project = client.post("/api/projects", json={"name": "Write the paper"}).json()
    from_book = note(client, "From book", book_id=summa["id"])
    assert from_book["book_id"] == summa["id"] and from_book["book_title"] == "Summa Theologiae"
    linked = note(client, "For project", project_id=project["id"], book_id=other_book["id"])
    assert linked["project_id"] == project["id"] and linked["project_name"] == "Write the paper"
    moved = client.patch(
        f"/api/notes/{from_book['id']}",
        json={
            "book_id": other_book["id"],
            "project_id": project["id"],
        },
    ).json()
    assert moved["book_title"] == "Confessions" and moved["project_name"] == "Write the paper"
    cleared = client.patch(
        f"/api/notes/{from_book['id']}",
        json={
            "book_id": None,
            "project_id": None,
        },
    ).json()
    assert cleared["book_id"] is None and cleared["project_id"] is None
    assert cleared["book_title"] is None and cleared["project_name"] is None
    assert client.get(f"/api/notes?book_id={other_book['id']}").json()[0]["id"] == linked["id"]
    by_project = client.get(f"/api/notes?project_id={project['id']}").json()
    assert [item["id"] for item in by_project] == [linked["id"]]
    # Project notes from the earlier module are a separate system and are untouched.
    assert client.get(f"/api/projects/{project['id']}/notes").json() == []


def test_notes_search_and_filtering(client):
    summa = book(client)
    project = client.post("/api/projects", json={"name": "Paper"}).json()
    a = note(
        client,
        "Natural law",
        content="Participation in the eternal law",
        note_type="reading_note",
        book_id=summa["id"],
        tags=["law", "ethics"],
        source_location="ST I-II, q. 91",
    )
    b = note(
        client, "What is virtue?", note_type="question", tags=["ethics"], project_id=project["id"]
    )
    c = note(client, "Weather", content="100% sunny_day", note_type="general")

    def ids(query):
        return {item["id"] for item in client.get(f"/api/notes?{query}").json()}

    assert ids("") == {a["id"], b["id"], c["id"]}
    assert ids("q=eternal") == {a["id"]}
    assert ids("q=VIRTUE") == {b["id"]}
    assert ids("q=q.%2091") == {a["id"]}  # source location is searchable
    assert ids("q=law") == {a["id"]}  # title/content/tags
    assert ids("q=ethic") == {a["id"], b["id"]}  # partial tag match
    assert ids("tag=ETHICS") == {a["id"], b["id"]}
    assert ids("tag=law") == {a["id"]}
    assert ids("note_type=question") == {b["id"]}
    assert ids("note_type=reading_note&q=natural") == {a["id"]}
    assert ids(f"book_id={summa['id']}") == {a["id"]}
    assert ids(f"project_id={project['id']}") == {b["id"]}
    assert ids("q=%25") == {c["id"]} and ids("q=_") == {c["id"]}
    assert ids("q=zzz") == set()
    assert client.get("/api/notes?note_type=summary").status_code == 422
    newest_first = [item["id"] for item in client.get("/api/notes").json()]
    assert newest_first[0] == c["id"]


def test_deleting_a_book_never_deletes_its_notes(client, application):
    summa = book(client, "Summa Theologiae", authors=["Thomas Aquinas"])
    first = note(
        client, "Quote", note_type="quotation", book_id=summa["id"], source_location="I, q. 2"
    )
    second = note(client, "Paraphrase", note_type="reading_note", book_id=summa["id"])
    path = f"/api/books/{summa['id']}"
    refused = client.delete(path)
    assert refused.status_code == 409 and "2 notes are linked" in refused.json()["detail"]
    assert client.get(path).status_code == 200
    assert client.delete(path + "?keep_notes=true").status_code == 204
    assert client.get(path).status_code == 404
    for original in (first, second):
        kept = client.get(f"/api/notes/{original['id']}").json()
        assert kept["title"] == original["title"] and kept["content"] == original["content"]
        assert kept["book_id"] is None and kept["former_book"] == "Summa Theologiae"
    assert client.get(f"/api/notes/{first['id']}").json()["source_location"] == "I, q. 2"
    with application.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Note)) == 2
    relinked = book(client, "Summa, 2nd copy")
    assert (
        client.patch(f"/api/notes/{first['id']}", json={"book_id": relinked["id"]}).json()[
            "former_book"
        ]
        is None
    )
    assert client.delete(f"/api/books/{book(client, 'Empty')['id']}").status_code == 204


def test_deleting_a_project_keeps_the_notes_that_mentioned_it(client):
    project = client.post("/api/projects", json={"name": "Doomed"}).json()
    kept = note(client, "Keep me", project_id=project["id"])
    assert client.delete(f"/api/projects/{project['id']}").status_code == 204
    survivor = client.get(f"/api/notes/{kept['id']}").json()
    assert survivor["title"] == "Keep me" and survivor["project_id"] is None


# ---------------------------------------------------------------- connections


def test_connect_view_from_both_ends_and_remove(client):
    a, b = note(client, "A"), note(client, "B")
    created = connect(client, a, b, "supports", explanation="  B's premise grounds A  ")
    assert created.status_code == 201, created.text
    link = created.json()
    assert link["link_type"] == "supports" and link["direction"] == "outgoing"
    assert link["explanation"] == "B's premise grounds A" and link["note"]["id"] == b["id"]
    assert link["created_at"].endswith("Z")
    from_a = client.get(f"/api/notes/{a['id']}/connections").json()
    from_b = client.get(f"/api/notes/{b['id']}/connections").json()
    assert [(c["id"], c["direction"], c["note"]["title"]) for c in from_a] == [
        (link["id"], "outgoing", "B")
    ]
    assert [(c["id"], c["direction"], c["note"]["title"]) for c in from_b] == [
        (link["id"], "incoming", "A")
    ]
    assert from_b[0]["explanation"] == "B's premise grounds A"
    assert client.delete(f"/api/note-links/{link['id']}").status_code == 204
    assert client.get(f"/api/notes/{a['id']}/connections").json() == []
    assert client.get(f"/api/notes/{b['id']}/connections").json() == []
    assert client.delete(f"/api/note-links/{link['id']}").status_code == 404
    assert client.get(f"/api/notes/{a['id']}").status_code == 200  # notes survive link removal


@pytest.mark.parametrize("link_type", ["supports", "develops", "responds_to"])
def test_directional_relationships_are_not_symmetric(client, link_type):
    a, b = note(client, "A"), note(client, "B")
    assert connect(client, a, b, link_type).status_code == 201
    assert [c["direction"] for c in client.get(f"/api/notes/{a['id']}/connections").json()] == [
        "outgoing"
    ]
    assert [c["direction"] for c in client.get(f"/api/notes/{b['id']}/connections").json()] == [
        "incoming"
    ]
    assert connect(client, a, b, link_type).status_code == 409  # same direction: duplicate
    reverse = connect(client, b, a, link_type)  # B -> A is a different fact
    assert reverse.status_code == 201 and reverse.json()["direction"] == "outgoing"
    assert len(client.get(f"/api/notes/{a['id']}/connections").json()) == 2


@pytest.mark.parametrize("link_type", ["related_to", "contradicts"])
def test_symmetric_relationships_are_stored_once_and_read_the_same_both_ways(client, link_type):
    a, b = note(client, "A"), note(client, "B")
    assert connect(client, a, b, link_type).status_code == 201
    assert connect(client, b, a, link_type).status_code == 409  # B -> A would repeat it
    assert connect(client, a, b, link_type).status_code == 409
    for note_id in (a["id"], b["id"]):
        listed = client.get(f"/api/notes/{note_id}/connections").json()
        assert [c["direction"] for c in listed] == ["mutual"]


def test_different_relationship_types_may_coexist_between_the_same_notes(client):
    a, b = note(client, "A"), note(client, "B")
    for link_type in ("related_to", "supports", "develops", "contradicts", "responds_to"):
        assert connect(client, a, b, link_type).status_code == 201, link_type
    assert len(client.get(f"/api/notes/{b['id']}/connections").json()) == 5


def test_self_links_and_bad_input_are_rejected(client):
    a, b = note(client, "A"), note(client, "B")
    assert connect(client, a, a).status_code == 422
    assert connect(client, a, {"id": str(uuid4())}).status_code == 404
    for payload in (
        {"link_type": "supports"},
        {"target_note_id": b["id"], "link_type": "likes"},
        {"target_note_id": b["id"], "link_type": "supports", "x": 1},
        {"target_note_id": b["id"], "link_type": "supports", "explanation": "x" * 5001},
    ):
        assert client.post(f"/api/notes/{a['id']}/connections", json=payload).status_code == 422
    assert client.get(f"/api/notes/{a['id']}/connections").json() == []


def test_database_refuses_self_links_and_duplicates_even_without_the_api(client, application):
    a, b = note(client, "A"), note(client, "B")
    with application.state.session_factory() as db:
        user_id = db.scalar(select(User.id))
    from uuid import UUID

    with pytest.raises(IntegrityError), application.state.session_factory.begin() as db:
        db.add(
            NoteLink(
                user_id=user_id,
                source_note_id=UUID(a["id"]),
                target_note_id=UUID(a["id"]),
                link_type="supports",
            )
        )
    with application.state.session_factory.begin() as db:
        db.add(
            NoteLink(
                user_id=user_id,
                source_note_id=UUID(a["id"]),
                target_note_id=UUID(b["id"]),
                link_type="supports",
            )
        )
    with pytest.raises(IntegrityError), application.state.session_factory.begin() as db:
        db.add(
            NoteLink(
                user_id=user_id,
                source_note_id=UUID(a["id"]),
                target_note_id=UUID(b["id"]),
                link_type="supports",
            )
        )


def test_deleting_a_note_removes_its_connections_but_not_the_other_note(client, application):
    a, b, c = note(client, "A"), note(client, "B"), note(client, "C")
    connect(client, a, b, "develops")
    connect(client, c, a, "responds_to")
    assert client.delete(f"/api/notes/{a['id']}").status_code == 204
    assert client.get(f"/api/notes/{b['id']}/connections").json() == []
    assert client.get(f"/api/notes/{c['id']}/connections").json() == []
    assert client.get(f"/api/notes/{b['id']}").status_code == 200
    with application.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(NoteLink)) == 0


def test_graph_endpoint_exposes_notes_as_nodes_and_connections_as_edges(client):
    summa = book(client)
    a, b, c = note(client, "A", book_id=summa["id"]), note(client, "B"), note(client, "C")
    directional = connect(client, a, b, "develops").json()
    mutual = connect(client, c, b, "related_to").json()
    graph = client.get("/api/notes/graph").json()
    assert {n["id"] for n in graph["nodes"]} == {a["id"], b["id"], c["id"]}
    assert next(n for n in graph["nodes"] if n["id"] == a["id"])["book_id"] == summa["id"]
    edges = {e["id"]: e for e in graph["edges"]}
    assert (
        edges[directional["id"]]["source"] == a["id"]
        and edges[directional["id"]]["target"] == b["id"]
    )
    assert (
        edges[directional["id"]]["symmetric"] is False and edges[mutual["id"]]["symmetric"] is True
    )
    assert {edges[mutual["id"]]["source"], edges[mutual["id"]]["target"]} == {b["id"], c["id"]}


# ---------------------------------------------------------------- ownership and persistence


def test_other_users_data_is_invisible_and_untouchable(client, application):
    mine = note(client, "Mine")
    my_book = book(client, "My book")
    my_project = client.post("/api/projects", json={"name": "Mine"}).json()
    foreign_user = uuid4()
    with application.state.session_factory.begin() as db:
        db.add(User(id=foreign_user, timezone="UTC"))
        db.flush()
        foreign_book = Book(user_id=foreign_user, title="Private book", authors=[])
        foreign_project = Project(user_id=foreign_user, name="Private project")
        db.add_all([foreign_book, foreign_project])
        db.flush()
        theirs = Note(
            user_id=foreign_user, title="Private note", content="secret", book_id=foreign_book.id
        )
        other = Note(user_id=foreign_user, title="Other private", content="")
        db.add_all([theirs, other])
        db.flush()
        link = NoteLink(
            user_id=foreign_user,
            source_note_id=theirs.id,
            target_note_id=other.id,
            link_type="supports",
        )
        db.add(link)
        db.flush()
        ids = {
            "book": str(foreign_book.id),
            "project": str(foreign_project.id),
            "note": str(theirs.id),
            "link": str(link.id),
        }
    assert [n["title"] for n in client.get("/api/notes").json()] == ["Mine"]
    assert [b["title"] for b in client.get("/api/books").json()] == ["My book"]
    assert client.get("/api/notes?q=secret").json() == []
    assert client.get("/api/notes/graph").json()["edges"] == []
    for method, path, payload in [
        ("get", f"/api/books/{ids['book']}", None),
        ("patch", f"/api/books/{ids['book']}", {"title": "stolen"}),
        ("delete", f"/api/books/{ids['book']}?keep_notes=true", None),
        ("get", f"/api/notes/{ids['note']}", None),
        ("patch", f"/api/notes/{ids['note']}", {"title": "stolen"}),
        ("delete", f"/api/notes/{ids['note']}", None),
        ("get", f"/api/notes/{ids['note']}/connections", None),
        (
            "post",
            f"/api/notes/{ids['note']}/connections",
            {"target_note_id": mine["id"], "link_type": "supports"},
        ),
        (
            "post",
            f"/api/notes/{mine['id']}/connections",
            {"target_note_id": ids["note"], "link_type": "supports"},
        ),
        ("delete", f"/api/note-links/{ids['link']}", None),
        ("post", "/api/notes", {"title": "x", "book_id": ids["book"]}),
        ("post", "/api/notes", {"title": "x", "project_id": ids["project"]}),
        ("patch", f"/api/notes/{mine['id']}", {"book_id": ids["book"]}),
        ("patch", f"/api/notes/{mine['id']}", {"project_id": ids["project"]}),
    ]:
        response = client.request(
            method, path, json=payload, headers={"X-User-ID": str(foreign_user)}
        )
        assert response.status_code == 404, (method, path, response.status_code)
    assert my_book["id"] and my_project["id"]
    with application.state.session_factory() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(Note)
                .where(
                    Note.user_id == foreign_user,
                    Note.title == "Private note",
                )
            )
            == 1
        )
        assert db.scalar(select(func.count()).select_from(NoteLink)) == 1


def test_everything_persists_across_application_instances(client, application):
    summa = book(client, authors=["Thomas Aquinas"])
    a = note(
        client,
        "A",
        book_id=summa["id"],
        tags=["law"],
        note_type="quotation",
        source_location="q. 1",
    )
    b = note(client, "B")
    link = connect(client, a, b, "develops", explanation="Because").json()
    clone = create_app(application.state.settings)
    with TestClient(clone) as second:
        assert second.get(f"/api/books/{summa['id']}").json()["note_count"] == 1
        reread = second.get(f"/api/notes/{a['id']}").json()
        assert reread["tags"] == ["law"] and reread["source_location"] == "q. 1"
        assert second.get(f"/api/notes/{b['id']}/connections").json()[0]["id"] == link["id"]
        assert second.get(f"/api/notes?book_id={summa['id']}").json()[0]["id"] == a["id"]


def test_migration_0005_keeps_existing_data_and_round_trips(application):
    with application.state.session_factory.begin() as db:
        user = User(id=uuid4(), timezone="UTC")
        db.add(user)
        db.flush()
        db.add(Project(user_id=user.id, name="Existing project"))
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with application.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0004")
        tables = set(sa.inspect(connection).get_table_names())
        assert not tables & {"books", "notes", "note_tags", "note_links"}
        assert connection.scalar(sa.text("SELECT name FROM projects")) == "Existing project"
        command.upgrade(config, "head")
        tables = set(sa.inspect(connection).get_table_names())
        assert {"books", "notes", "note_tags", "note_links"} <= tables
        assert connection.scalar(sa.text("SELECT name FROM projects")) == "Existing project"
