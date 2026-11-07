import csv
import io
import urllib.error
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models import Book, Note, NoteLink, User
from app.services import covers, goodreads
from app.services.goodreads import isbn10_to_13

HEADER = [
    "Book Id",
    "Title",
    "Author",
    "Author l-f",
    "Additional Authors",
    "ISBN",
    "ISBN13",
    "My Rating",
    "Average Rating",
    "Publisher",
    "Binding",
    "Number of Pages",
    "Year Published",
    "Original Publication Year",
    "Date Read",
    "Date Added",
    "Bookshelves",
    "Bookshelves with positions",
    "Exclusive Shelf",
    "My Review",
    "Spoiler",
    "Private Notes",
    "Read Count",
    "Owned Copies",
]


def isbn13(seed: int) -> str:
    body = f"978{seed:09d}"
    total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(body))
    return body + str((10 - total % 10) % 10)


def isbn10(seed: int) -> str:
    body = f"{seed:09d}"
    total = sum((10 - i) * int(d) for i, d in enumerate(body))
    check = (11 - total % 11) % 11
    return body + ("X" if check == 10 else str(check))


def make_csv(rows, columns=HEADER, bom=False) -> bytes:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=columns, extrasaction="ignore", lineterminator="\r\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    data = out.getvalue().encode("utf-8")
    return b"\xef\xbb\xbf" + data if bom else data


def gr(book_id, title, author, **extra):
    row = {
        "Book Id": str(book_id),
        "Title": title,
        "Author": author,
        "My Rating": "5",
        "Average Rating": "4.2",
        "Exclusive Shelf": "read",
        "Bookshelves": "favorites, philosophy",
        "Date Read": "2020/01/02",
        "Date Added": "2019/12/31",
        "Read Count": "1",
        "My Review": "Loved it, <b>truly</b>.",
        "Private Notes": "secret",
    }
    row.update(extra)
    return row


def preview(client, content):
    return client.post(
        "/api/books/import/preview",
        content=content,
        headers={"Content-Type": "text/csv"},
    )


def confirm(client, token):
    return client.post("/api/books/import/confirm", json={"token": token})


def run_import(client, content):
    previewed = preview(client, content)
    assert previewed.status_code == 200, previewed.text
    done = confirm(client, previewed.json()["token"])
    assert done.status_code == 200, done.text
    return done.json()


def library(application):
    with application.state.session_factory() as db:
        return {
            "books": db.scalar(select(func.count()).select_from(Book)),
            "notes": db.scalar(select(func.count()).select_from(Note)),
            "links": db.scalar(select(func.count()).select_from(NoteLink)),
        }


def make_book(client, title, **kwargs):
    response = client.post("/api/books", json={"title": title, **kwargs})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture(autouse=True)
def no_live_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("Tests must not reach Open Library")

    monkeypatch.setattr(covers.urllib.request, "urlopen", refuse)
    monkeypatch.setattr(covers, "PACER", covers.Pacer(0))


# ----------------------------------------------------------------- parsing and preview


def test_preview_maps_bibliographic_fields_and_writes_nothing(client, application):
    content = make_csv(
        [
            gr(
                101,
                "The Republic",
                "Plato",
                **{
                    "Additional Authors": "Allan Bloom, Benjamin Jowett",
                    "ISBN": f'="{isbn10(123456789)}"',
                    "ISBN13": f'="{isbn13(123456789)}"',
                    "Publisher": "Basic Books",
                    "Binding": "Paperback",
                    "Year Published": "1991",
                    "Original Publication Year": "-380",
                },
            ),
            gr(
                102,
                "Confessions",
                "Augustine of Hippo",
                **{
                    "ISBN13": "",
                    "Publisher": "Oxford",
                    "Year Published": "",
                    "Original Publication Year": "397",
                },
            ),
            gr(103, "Summa Theologiae (Vol. 1)", "Thomas Aquinas", **{"Year Published": "0"}),
        ],
        bom=True,
    )
    response = preview(client, content)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["counts"] == {
        "total_rows": 3,
        "to_add": 3,
        "matched": 0,
        "to_update": 0,
        "duplicates": 0,
        "ambiguous": 0,
        "invalid": 0,
    }
    assert [item["title"] for item in body["sample_new"]] == [
        "The Republic",
        "Confessions",
        "Summa Theologiae (Vol. 1)",
    ]
    assert body["sample_new"][0]["authors"] == ["Plato", "Allan Bloom", "Benjamin Jowett"]
    assert library(application) == {"books": 0, "notes": 0, "links": 0}  # preview writes nothing

    result = confirm(client, body["token"]).json()
    assert result["summary"]["added"] == 3 and result["summary"]["skipped"] == 0
    stored = {b["title"]: b for b in client.get("/api/books").json()["items"]}
    republic = stored["The Republic"]
    assert republic["authors"] == ["Plato", "Allan Bloom", "Benjamin Jowett"]
    assert republic["isbn_13"] == isbn13(123456789) and republic["isbn_10"] == isbn10(123456789)
    assert republic["publication_year"] == 1991 and republic["publisher"] == "Basic Books"
    assert republic["edition"] == "Paperback" and republic["goodreads_id"] == "101"
    assert republic["cover_url"] is None
    assert stored["Confessions"]["publication_year"] == 397  # falls back to the original year
    assert stored["Summa Theologiae (Vol. 1)"]["publication_year"] is None  # "0" is not a year
    for forbidden in (
        "rating",
        "shelf",
        "bookshelves",
        "date_read",
        "review",
        "status",
        "read_count",
    ):
        assert not any(forbidden in key for key in republic)
    assert "truly" not in str(stored) and "secret" not in str(stored)  # reviews are never kept


def test_missing_optional_columns_are_fine(client):
    content = make_csv(
        [gr(1, "Pensées", "Blaise Pascal"), gr(2, "Provincial Letters", "Blaise Pascal")],
        columns=["Book Id", "Title", "Author"],
    )
    body = preview(client, content).json()
    assert body["counts"]["to_add"] == 2 and body["counts"]["invalid"] == 0
    assert confirm(client, body["token"]).status_code == 200
    stored = client.get("/api/books?q=pens").json()["items"][0]
    assert stored["isbn_13"] is None and stored["publisher"] is None and stored["edition"] is None
    assert stored["publication_year"] is None and stored["authors"] == ["Blaise Pascal"]


def test_a_row_without_a_title_is_reported_and_the_rest_still_imports(client):
    content = make_csv([gr(1, "Good", "A"), gr(2, "", "B"), gr(3, "   ", "C")])
    body = preview(client, content).json()
    assert body["counts"]["total_rows"] == 3 and body["counts"]["to_add"] == 1
    assert body["counts"]["invalid"] == 2
    invalid = [p for p in body["problems"] if p["kind"] == "invalid"]
    assert {p["row"] for p in invalid} == {3, 4} and "no title" in invalid[0]["message"]


@pytest.mark.parametrize(
    "content,fragment",
    [
        (b"", "empty"),
        (b"   \r\n  ", "empty"),
        (make_csv([]), "No books"),
        (b"name,age\r\nAda,36\r\n", "Goodreads"),
        (b"Book Id,Author\r\n1,Someone\r\n", "Goodreads"),
        (b"\x00\x01\x02binary\x00", "CSV text"),
        (b"Book Id,Title,Author\r\n1,Caf\xe9,Someone\r\n", "UTF-8"),
        (b'Book Id,Title,Author\r\n1,"Unclosed,Someone\r\n', "valid CSV"),
    ],
)
def test_unusable_files_get_a_helpful_422_and_change_nothing(
    client, application, content, fragment
):
    response = preview(client, content)
    assert response.status_code == 422, response.text
    assert fragment in response.json()["detail"]
    assert library(application)["books"] == 0


def test_file_size_and_row_limits(client, application, monkeypatch):
    monkeypatch.setattr(goodreads, "MAX_ROWS", 3)
    too_many = make_csv([gr(i, f"Book {i}", "A") for i in range(4)])
    response = preview(client, too_many)
    assert response.status_code == 422 and "more than 3 books" in response.json()["detail"]
    monkeypatch.undo()
    monkeypatch.setattr("app.api.routes.book_import.MAX_BYTES", 200)
    huge = make_csv([gr(i, "x" * 50, "A") for i in range(20)])
    assert preview(client, huge).status_code == 413
    assert library(application)["books"] == 0


@pytest.mark.parametrize(
    "raw,expected_10,expected_13,warned",
    [
        ('="9780306406157"', None, "9780306406157", False),
        ('="0306406152"', "0306406152", None, False),
        ("978-0-306-40615-7", None, "9780306406157", False),
        ("0-8044-2957-X", "080442957X", None, False),
        ("9780306406158", None, None, True),  # bad check digit: never stored
        ("0306406153", None, None, True),
        ('=""', None, None, False),
        ("", None, None, False),
        ("not-an-isbn", None, None, True),
    ],
)
def test_isbn_normalization_never_introduces_invalid_identifiers(
    client, raw, expected_10, expected_13, warned
):
    columns = ["Book Id", "Title", "Author", "ISBN", "ISBN13"]
    # the same value in either column is understood by what it is, not where it sits
    body = preview(client, make_csv([gr(1, "Edition", "Author", ISBN=raw)], columns)).json()
    assert body["counts"]["to_add"] == 1
    assert any("invalid ISBN" in p["message"] for p in body["problems"]) is warned
    confirm(client, body["token"])
    stored = client.get("/api/books?q=edition").json()["items"][0]
    assert (stored["isbn_10"], stored["isbn_13"]) == (expected_10, expected_13)


def test_isbn_conversion_is_only_used_for_comparison(client):
    assert isbn10_to_13("0306406152") == "9780306406157"
    made = make_book(client, "Existing", authors=["A"], isbn_10="0306406152")
    body = preview(
        client, make_csv([gr(5, "Different Title", "Other", ISBN13=f'="{9780306406157}"')])
    ).json()
    assert body["counts"]["matched"] == 1 and body["sample_matched"][0]["book_id"] == made["id"]
    assert body["sample_matched"][0]["reason"] == "isbn"
    confirm(client, body["token"])
    after = client.get(f"/api/books/{made['id']}").json()
    assert after["isbn_10"] == "0306406152" and after["isbn_13"] == "9780306406157"
    assert after["title"] == "Existing"


# ----------------------------------------------------------------- duplicates and ambiguity


def test_duplicate_goodreads_ids_within_the_file(client):
    content = make_csv([gr(7, "Dup", "A"), gr(7, "Dup (again)", "A"), gr(8, "Other", "B")])
    body = preview(client, content).json()
    assert body["counts"]["to_add"] == 2 and body["counts"]["duplicates"] == 1
    assert [p["kind"] for p in body["problems"] if p["kind"] == "duplicate"] == ["duplicate"]
    assert confirm(client, body["token"]).json()["summary"]["added"] == 2
    assert len(client.get("/api/books").json()["items"]) == 2


def test_duplicate_isbns_without_goodreads_ids_are_one_book(client):
    content = make_csv(
        [
            gr("", "Same", "A", ISBN13=isbn13(5)),
            gr("", "Same, reissued", "A", ISBN13=isbn13(5)),
        ]
    )
    body = preview(client, content).json()
    assert body["counts"]["to_add"] == 1 and body["counts"]["duplicates"] == 1


def test_conflicting_identifiers_keep_distinct_editions_apart(client):
    first = make_book(
        client, "Meditations", authors=["Marcus Aurelius"], goodreads_id="G1", isbn_13=isbn13(9)
    )
    content = make_csv([gr("G2", "Meditations", "Marcus Aurelius", ISBN13=isbn13(9))])
    body = preview(client, content).json()
    assert body["counts"]["to_add"] == 1 and body["counts"]["matched"] == 0
    assert any("different Goodreads ID" in p["message"] for p in body["problems"])
    confirm(client, body["token"])
    assert len(client.get("/api/books").json()["items"]) == 2
    assert client.get(f"/api/books/{first['id']}").json()["goodreads_id"] == "G1"
    # two rows in one file with the same ISBN but different Goodreads IDs are also kept apart
    body = preview(
        client,
        make_csv(
            [
                gr("G3", "Edition A", "X", ISBN13=isbn13(11)),
                gr("G4", "Edition B", "X", ISBN13=isbn13(11)),
            ]
        ),
    ).json()
    assert body["counts"]["to_add"] == 2


def test_ambiguous_matches_are_flagged_not_guessed(client, application):
    make_book(client, "Twin", authors=["Same Author"])
    make_book(client, "Twin", authors=["Same Author"])
    make_book(client, "Cousin A", isbn_13=isbn13(21))
    make_book(client, "Cousin B", isbn_13=isbn13(21))
    content = make_csv(
        [
            gr("", "Twin", "Same Author"),
            gr("", "Whatever", "Z", ISBN13=isbn13(21)),
        ]
    )
    body = preview(client, content).json()
    assert body["counts"]["ambiguous"] == 2 and body["counts"]["to_add"] == 0
    assert body["counts"]["matched"] == 0
    result = confirm(client, body["token"]).json()["summary"]
    assert result["added"] == 0 and result["skipped"] == 2 and result["ambiguous"] == 2
    assert library(application)["books"] == 4


def test_similar_titles_are_never_merged(client):
    make_book(client, "The Republic", authors=["Plato"])
    make_book(client, "Republic", authors=["Plato"])
    content = make_csv(
        [
            gr(1, "The Republic of Letters", "Plato"),
            gr(2, "The Republic", "Cicero"),
            gr(3, "Republics", "Plato"),
        ]
    )
    body = preview(client, content).json()
    assert body["counts"]["to_add"] == 3 and body["counts"]["matched"] == 0


def test_title_and_author_match_only_when_unambiguous_and_unconflicted(client):
    mine = make_book(client, "Nicomachean Ethics", authors=["Aristotle"])
    content = make_csv([gr(31, "Nicomachean Ethics (Hackett Classics)", "Aristotle")])
    body = preview(client, content).json()
    assert body["counts"]["matched"] == 1 and body["sample_matched"][0]["reason"] == "title_author"
    assert body["sample_matched"][0]["book_id"] == mine["id"]
    confirm(client, body["token"])
    assert client.get(f"/api/books/{mine['id']}").json()["goodreads_id"] == "31"
    # a different Goodreads ID for the same title and author is a different record
    body = preview(client, make_csv([gr(32, "Nicomachean Ethics", "Aristotle")])).json()
    assert body["counts"]["to_add"] == 1 and body["counts"]["matched"] == 0


# ----------------------------------------------------------------- idempotency and protection


def test_importing_the_same_file_twice_creates_no_duplicates(client, application):
    content = make_csv(
        [
            gr(1, "One", "A", ISBN13=isbn13(1)),
            gr(2, "Two", "B"),
            gr(3, "Three", "C", ISBN=isbn10(3)),
        ]
    )
    first = run_import(client, content)
    assert first["summary"]["added"] == 3
    assert library(application)["books"] == 3
    again = preview(client, content).json()
    assert again["counts"]["to_add"] == 0 and again["counts"]["matched"] == 3
    assert again["counts"]["to_update"] == 0
    second = confirm(client, again["token"]).json()["summary"]
    assert second["added"] == 0 and second["updated"] == 0 and second["matched"] == 3
    assert library(application)["books"] == 3
    assert confirm(client, again["token"]).status_code == 404  # a token works once


def test_matched_books_only_gain_missing_fields(client):
    manual = make_book(
        client,
        "Summa",
        authors=["Thomas Aquinas"],
        publisher="My Own Press",
        description="My own description",
        cover_url="https://example.com/mine.jpg",
    )
    path = f"/api/books/{manual['id']}"
    content = make_csv(
        [
            gr(
                88,
                "Summa (Complete)",
                "Thomas Aquinas",
                Publisher="Someone Else",
                **{
                    "Year Published": "1274",
                    "ISBN13": f'="{isbn13(88)}"',
                    "Binding": "Hardcover",
                },
            )
        ]
    )
    result = run_import(client, content)["summary"]
    assert result["matched"] == 1 and result["updated"] == 1 and result["added"] == 0
    after = client.get(path).json()
    assert after["publisher"] == "My Own Press"  # not replaced
    assert after["title"] == "Summa" and after["authors"] == ["Thomas Aquinas"]
    assert after["description"] == "My own description"
    assert after["cover_url"] == "https://example.com/mine.jpg"
    assert after["publication_year"] == 1274 and after["isbn_13"] == isbn13(88)  # filled
    assert after["goodreads_id"] == "88" and after["edition"] == "Hardcover"
    # editing by hand and importing again leaves the hand edit alone
    client.patch(path, json={"publisher": "Hand edited", "publication_year": 1999})
    run_import(client, content)
    final = client.get(path).json()
    assert final["publisher"] == "Hand edited" and final["publication_year"] == 1999


def test_existing_notes_and_connections_survive_an_import(client, application):
    book = make_book(client, "Summa Theologiae", authors=["Thomas Aquinas"], goodreads_id="555")
    first = client.post(
        "/api/notes",
        json={
            "title": "Quote",
            "note_type": "quotation",
            "book_id": book["id"],
            "source_location": "I, q. 2",
            "content": "Exact words.",
        },
    ).json()
    second = client.post(
        "/api/notes",
        json={
            "title": "Reflection",
            "note_type": "reflection",
            "book_id": book["id"],
            "content": "Mine.",
        },
    ).json()
    link = client.post(
        f"/api/notes/{first['id']}/connections",
        json={
            "target_note_id": second["id"],
            "link_type": "develops",
            "explanation": "because",
        },
    ).json()
    before = library(application)
    content = make_csv([gr(555, "Summa Theologiae", "Thomas Aquinas", Publisher="Ave Maria")])
    summary = run_import(client, content)["summary"]
    assert summary["matched"] == 1 and summary["added"] == 0
    assert library(application) == before
    notes = client.get(f"/api/notes?book_id={book['id']}").json()
    assert {n["id"] for n in notes} == {first["id"], second["id"]}
    assert client.get(f"/api/notes/{first['id']}").json()["content"] == "Exact words."
    assert client.get(f"/api/notes/{first['id']}").json()["source_location"] == "I, q. 2"
    connections = client.get(f"/api/notes/{first['id']}/connections").json()
    assert [c["id"] for c in connections] == [link["id"]]
    assert client.get(f"/api/books/{book['id']}").json()["note_count"] == 2


def test_books_missing_from_the_export_are_never_deleted(client, application):
    make_book(client, "Hand-added", authors=["Me"])
    run_import(client, make_csv([gr(1, "Imported", "A")]))
    titles = {b["title"] for b in client.get("/api/books").json()["items"]}
    assert titles == {"Hand-added", "Imported"}


# ----------------------------------------------------------------- ownership, cancel, failure


def test_other_users_books_and_previews_are_out_of_reach(client, application):
    foreign = uuid4()
    with application.state.session_factory.begin() as db:
        db.add(User(id=foreign, timezone="UTC"))
        db.flush()
        theirs = Book(
            user_id=foreign, title="Shared Title", authors=["Shared Author"], goodreads_id="42"
        )
        db.add(theirs)
        db.flush()
        theirs_id = theirs.id
    run_import(client, make_csv([gr(42, "Shared Title", "Shared Author")]))
    assert [b["title"] for b in client.get("/api/books").json()["items"]] == [
        "Shared Title"
    ]  # mine only
    with application.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Book)) == 2
        untouched = db.get(Book, theirs_id)
        assert untouched.user_id == foreign and untouched.publisher is None
    rows = goodreads.parse_export(make_csv([gr(99, "Secret", "S")])).rows
    stolen = application.state.import_store.put(foreign, rows)
    assert confirm(client, stolen).status_code == 404
    assert (
        client.delete(f"/api/books/import/{stolen}").status_code == 204
    )  # cannot cancel it either
    assert application.state.import_store.get(foreign, stolen) is not None
    assert [b["title"] for b in client.get("/api/books?q=secret").json()["items"]] == []


def test_cancelling_or_abandoning_a_preview_changes_nothing(client, application):
    content = make_csv([gr(1, "One", "A"), gr(2, "Two", "B")])
    token = preview(client, content).json()["token"]
    assert library(application)["books"] == 0
    assert client.delete(f"/api/books/import/{token}").status_code == 204
    assert confirm(client, token).status_code == 404
    assert client.delete(f"/api/books/import/{token}").status_code == 204  # idempotent
    expiring = preview(client, content).json()["token"]
    application.state.import_store.clock = lambda: 10**9
    response = confirm(client, expiring)
    assert response.status_code == 404 and "expired" in response.json()["detail"]
    assert library(application)["books"] == 0
    assert confirm(client, "not-a-real-token").status_code == 404
    assert client.post("/api/books/import/confirm", json={"token": "x"}).status_code == 422


def test_clients_cannot_substitute_their_own_book_records(client, application):
    token = preview(client, make_csv([gr(1, "Real", "A")])).json()["token"]
    forged = client.post(
        "/api/books/import/confirm",
        json={
            "token": token,
            "books": [{"title": "Injected"}],
        },
    )
    assert forged.status_code == 422
    assert confirm(client, token).json()["books"][0]["title"] == "Real"
    assert [b["title"] for b in client.get("/api/books").json()["items"]] == ["Real"]


def test_a_failure_part_way_rolls_back_the_whole_import(client, application, monkeypatch):
    existing = make_book(client, "Existing", authors=["Someone"])
    content = make_csv(
        [
            gr(1, "Existing", "Someone", Publisher="Would be filled", **{"Year Published": "1900"}),
            gr(2, "New one", "A"),
            gr(3, "New two", "B"),
            gr(4, "New three", "C"),
        ]
    )
    token = preview(client, content).json()["token"]
    original = goodreads.make_book
    calls = {"count": 0}

    def flaky(user_id, row):
        calls["count"] += 1
        if calls["count"] == 3:
            raise RuntimeError("disk exploded")
        return original(user_id, row)

    monkeypatch.setattr(goodreads, "make_book", flaky)
    broken = TestClient(application, raise_server_exceptions=False)
    response = broken.post("/api/books/import/confirm", json={"token": token})
    assert response.status_code == 500
    assert library(application)["books"] == 1  # no partial additions
    untouched = client.get(f"/api/books/{existing['id']}").json()
    assert (
        untouched["publisher"] is None and untouched["publication_year"] is None
    )  # no partial fills
    monkeypatch.setattr(goodreads, "make_book", original)
    retried = confirm(client, token)  # the preview is still good
    assert retried.status_code == 200 and retried.json()["summary"]["added"] == 3
    assert library(application)["books"] == 4


def test_importing_leaves_the_rest_of_the_library_working(client):
    run_import(client, make_csv([gr(1, "Imported", "A")]))
    imported = client.get("/api/books").json()["items"][0]
    created = client.post("/api/notes", json={"title": "On it", "book_id": imported["id"]})
    assert created.status_code == 201
    assert client.get(f"/api/books/{imported['id']}").json()["note_count"] == 1
    assert client.delete(f"/api/books/{imported['id']}?keep_notes=true").status_code == 204


# ----------------------------------------------------------------- covers


def fake_lookup(table, calls=None):
    def lookup(isbn):
        if calls is not None:
            calls.append(isbn)
        return covers.Lookup(table.get(isbn, covers.NOT_FOUND))

    return lookup


def test_cover_enrichment_fills_only_missing_covers(client, monkeypatch):
    mine = make_book(
        client, "Hand picked", isbn_13=isbn13(1), cover_url="https://example.com/mine.jpg"
    )
    needs = make_book(client, "Needs cover", isbn_13=isbn13(2))
    none = make_book(client, "No cover exists", isbn_10=isbn10(3))
    no_isbn = make_book(client, "No ISBN")
    calls = []
    monkeypatch.setattr(
        covers,
        "lookup_cover",
        fake_lookup({isbn13(1): covers.FOUND, isbn13(2): covers.FOUND}, calls),
    )
    assert client.get("/api/books/covers/missing").json()["count"] == 2
    result = client.post("/api/books/covers/enrich", json={}).json()
    assert result["found"] == 1 and result["not_found"] == 1 and result["errors"] == 0
    assert [u["id"] for u in result["updated"]] == [needs["id"]]
    assert (
        result["updated"][0]["cover_url"]
        == f"https://covers.openlibrary.org/b/isbn/{isbn13(2)}-M.jpg"
    )
    assert sorted(calls) == sorted([isbn13(2), isbn10(3)])  # never asks about a book with a cover
    assert (
        client.get(f"/api/books/{mine['id']}").json()["cover_url"] == "https://example.com/mine.jpg"
    )
    assert client.get(f"/api/books/{none['id']}").json()["cover_url"] is None
    assert client.get(f"/api/books/{no_isbn['id']}").json()["cover_url"] is None
    # the no-cover book plus the freshly filled one, whose ISBN link has no verified cover ID yet
    assert set(result["checked_ids"]) == {none["id"], needs["id"]} and result["remaining"] == 0


def test_enrichment_is_bounded_resumable_and_asks_once_per_isbn(client, monkeypatch):
    shared = isbn13(50)
    make_book(client, "A twin", isbn_13=shared)
    make_book(client, "B twin", isbn_13=shared)
    for number in range(6):
        make_book(client, f"Solo {number}", isbn_13=isbn13(60 + number))
    calls = []
    monkeypatch.setattr(covers, "lookup_cover", fake_lookup({}, calls))
    first = client.post("/api/books/covers/enrich", json={"limit": 3}).json()
    assert first["checked"] == 3 and len(calls) == 3 and first["remaining"] > 0
    skip = first["checked_ids"]
    done = 3
    for _ in range(5):
        step = client.post("/api/books/covers/enrich", json={"limit": 3, "skip": skip}).json()
        skip += step["checked_ids"]
        if step["remaining"] == 0:
            break
    assert step["remaining"] == 0
    assert calls.count(shared) == 1 and len(calls) == 7  # the shared ISBN was asked once
    assert done == 3 and len(set(skip)) == len(skip)  # no book was checked twice


def test_failures_and_rate_limits_stop_the_batch_without_losing_anything(client, monkeypatch):
    real_now = covers.utcnow
    for number in range(5):
        make_book(client, f"Book {number}", isbn_13=isbn13(70 + number))
    calls = []
    monkeypatch.setattr(
        covers,
        "lookup_cover",
        fake_lookup({isbn13(70): covers.FOUND, isbn13(71): covers.RATE_LIMITED}, calls),
    )
    limited = client.post("/api/books/covers/enrich", json={"limit": 5}).json()
    assert limited["rate_limited"] and limited["stopped_early"] and limited["found"] == 1
    assert len(calls) == 2  # stopped at the 429
    monkeypatch.setattr(covers, "utcnow", lambda: real_now() + timedelta(days=1))  # cooldown over
    monkeypatch.setattr(
        covers,
        "lookup_cover",
        fake_lookup(
            {isbn13(72): covers.ERROR, isbn13(73): covers.ERROR, isbn13(74): covers.FOUND}, calls
        ),
    )
    flaky = client.post("/api/books/covers/enrich", json={"limit": 5}).json()
    assert flaky["errors"] == 2 and flaky["stopped_early"] and not flaky["rate_limited"]
    assert flaky["found"] == 0
    assert all(
        book["cover_url"] is None or "70" in book["cover_url"]
        for book in client.get("/api/books").json()["items"]
    )


def test_cover_lookup_handles_success_missing_rate_limit_and_network_errors(monkeypatch):
    class Response:
        def __init__(self, status):
            self.status = status
            self.url = "https://covers.openlibrary.org/b/isbn/9780306406157-L.jpg?default=false"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def respond(outcome):
        def fake(request, timeout=None):
            assert timeout and timeout <= 5 and request.get_method() == "HEAD"
            assert "default=false" in request.full_url and "Studium" in request.get_header(
                "User-agent"
            )
            if isinstance(outcome, Exception):
                raise outcome
            return Response(outcome)

        return fake

    def http_error(code):
        return urllib.error.HTTPError("https://x", code, "msg", {}, None)

    for outcome, expected in [
        (200, covers.FOUND),
        (http_error(404), covers.NOT_FOUND),
        (http_error(429), covers.RATE_LIMITED),
        (http_error(503), covers.RATE_LIMITED),
        (http_error(500), covers.ERROR),
        (urllib.error.URLError("offline"), covers.ERROR),
        (TimeoutError(), covers.ERROR),
    ]:
        monkeypatch.setattr(covers.urllib.request, "urlopen", respond(outcome))
        assert covers.lookup_cover("9780306406157").status == expected


def test_enrichment_is_scoped_to_the_current_user(client, application, monkeypatch):
    foreign = uuid4()
    with application.state.session_factory.begin() as db:
        db.add(User(id=foreign, timezone="UTC"))
        db.flush()
        db.add(Book(user_id=foreign, title="Theirs", authors=[], isbn_13=isbn13(90)))
    monkeypatch.setattr(covers, "lookup_cover", fake_lookup({isbn13(90): covers.FOUND}))
    assert client.get("/api/books/covers/missing").json()["count"] == 0
    assert client.post("/api/books/covers/enrich", json={}).json()["checked"] == 0
    with application.state.session_factory() as db:
        assert db.scalar(select(Book.cover_url).where(Book.user_id == foreign)) is None
