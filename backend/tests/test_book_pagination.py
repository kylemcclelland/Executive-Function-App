import csv
import hashlib
import io
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.models import Book, Note, User

SAME_MOMENT = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)


def seed_library(client, application):
    """237 books with deliberate ties on title, year and creation time."""
    user_id = UUID(client.get("/api/user").json()["id"])
    books = []
    for number in range(100):
        books.append(
            Book(
                user_id=user_id,
                title=f"Alpha {number:03d}",
                authors=["Alpha Author"],
                publication_year=1900 + number % 20,
                created_at=SAME_MOMENT,
                updated_at=SAME_MOMENT,
            )
        )
    for number in range(30):  # identical titles: only the id can order these
        books.append(
            Book(
                user_id=user_id,
                title="Same Title",
                authors=["Twin"],
                publication_year=None if number % 3 == 0 else 1950,
                created_at=SAME_MOMENT,
                updated_at=SAME_MOMENT,
            )
        )
    for number in range(100):
        books.append(
            Book(
                user_id=user_id,
                title=f"Beta {number:03d}",
                authors=["Beta Author"],
                publisher="Beta Press",
                isbn_13=f"9780000{number:06d}"[:13],
                publication_year=1900 + number % 7,
                created_at=SAME_MOMENT + timedelta(minutes=number // 10),
                updated_at=SAME_MOMENT,
            )
        )
    for number in range(7):
        books.append(
            Book(
                user_id=user_id,
                title=f"Zz Last {number}",
                authors=["Zed"],
                publication_year=2000 + number,
                created_at=SAME_MOMENT,
                updated_at=SAME_MOMENT,
            )
        )
    foreign = uuid4()
    with application.state.session_factory.begin() as db:
        db.add(User(id=foreign, timezone="UTC"))
        db.flush()
        db.add_all(books)
        db.add_all(Book(user_id=foreign, title=f"Foreign {n}", authors=[]) for n in range(20))
        db.flush()
        for number in range(3):
            db.add(Note(user_id=user_id, title=f"On Alpha {number}", book_id=books[0].id))
    return foreign


def get_page(client, **params):
    response = client.get("/api/books", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def walk(client, **params):
    """Every page of a listing, in order."""
    first = get_page(client, page=1, **params)
    items = list(first["items"])
    for number in range(2, first["total_pages"] + 1):
        page = get_page(client, page=number, **params)
        assert page["page"] == number and page["total"] == first["total"]
        items += page["items"]
    return first, items


def database_books(application):
    with application.state.session_factory() as db:
        user_id = db.scalar(select(User.id).where(User.timezone == "UTC").order_by(User.created_at))
        return [book for book in db.scalars(select(Book).where(Book.user_id == user_id))]


def fingerprint(application):
    with application.state.session_factory() as db:
        rows = db.execute(
            select(Book.id, Book.title, Book.cover_url, Book.isbn_13, Book.updated_at).order_by(
                Book.id
            )
        ).all()
    return hashlib.sha256(repr(rows).encode()).hexdigest(), len(rows)


def hex_id(value) -> str:
    return str(value).replace("-", "")


def test_the_response_shape_and_defaults(client, application):
    seed_library(client, application)
    body = get_page(client)
    assert set(body) == {"items", "total", "page", "page_size", "total_pages"}
    assert (body["total"], body["page"], body["page_size"], body["total_pages"]) == (237, 1, 50, 5)
    assert len(body["items"]) == 50
    assert {"id", "title", "authors", "note_count", "cover_url"} <= set(body["items"][0])
    assert len(get_page(client, page_size=100)["items"]) == 100
    assert get_page(client, page_size=100)["total_pages"] == 3


@pytest.mark.parametrize(
    "params",
    [
        {"page_size": 101},
        {"page_size": 0},
        {"page_size": -5},
        {"page": 0},
        {"page": -1},
        {"page": "x"},
        {"page_size": "many"},
        {"sort": "random"},
        {"q": "x" * 201},
    ],
)
def test_invalid_parameters_are_rejected_not_guessed(client, application, params):
    seed_library(client, application)
    assert client.get("/api/books", params=params).status_code == 422


def test_first_middle_and_last_pages(client, application):
    seed_library(client, application)
    titles = sorted((b.title for b in database_books(application)), key=lambda t: (t.lower(), t))
    first, middle, last = (get_page(client, page=n) for n in (1, 3, 5))
    assert [len(p["items"]) for p in (first, middle, last)] == [50, 50, 37]
    assert [p["page"] for p in (first, middle, last)] == [1, 3, 5]
    assert first["items"][0]["title"] == titles[0] and first["items"][-1]["title"] == titles[49]
    assert (
        middle["items"][0]["title"] == titles[100] and middle["items"][-1]["title"] == titles[149]
    )
    assert last["items"][0]["title"] == titles[200] and last["items"][-1]["title"] == titles[-1]
    assert titles[-1].startswith("Zz Last")


def test_pages_add_up_to_the_database_with_no_duplicates(client, application):
    seed_library(client, application)
    everything = database_books(application)
    assert len(everything) == 237
    for page_size in (50, 100, 7, 99):
        first, items = walk(client, page_size=page_size)
        ids = [item["id"] for item in items]
        assert len(ids) == len(set(ids)) == first["total"] == 237
        assert set(ids) == {str(book.id) for book in everything}
        assert first["total_pages"] == -(-237 // page_size)


def sort_key(sort):
    def key(book):
        lowered = (book.title.lower(), book.title)
        stamp = book.created_at.timestamp()
        return {
            "title": lowered,
            "title_desc": None,
            "recent": (-stamp, *lowered),
            "year_desc": (book.publication_year is None, -(book.publication_year or 0), *lowered),
            "year_asc": (book.publication_year is None, book.publication_year or 0, *lowered),
        }[sort] + (hex_id(book.id),)

    return key


@pytest.mark.parametrize("sort", ["title", "title_desc", "recent", "year_desc", "year_asc"])
def test_every_sort_is_complete_deterministic_and_ends_with_the_id(client, application, sort):
    seed_library(client, application)
    books = database_books(application)
    if sort == "title_desc":
        # descending applies to the title keys only; the id tie-break stays ascending
        expected = sorted(books, key=lambda b: (b.title.lower(), b.title, hex_id(b.id)))
        groups: dict = {}
        for book in expected:
            groups.setdefault((book.title.lower(), book.title), []).append(book)
        expected = [b for key in sorted(groups, reverse=True) for b in groups[key]]
    else:
        expected = sorted(books, key=sort_key(sort))
    first, items = walk(client, sort=sort, page_size=50)
    ids = [item["id"] for item in items]
    assert len(ids) == len(set(ids)) == 237
    assert ids == [str(book.id) for book in expected]
    again = [item["id"] for item in walk(client, sort=sort, page_size=50)[1]]
    assert again == ids  # repeatable
    other_sizes = [item["id"] for item in walk(client, sort=sort, page_size=33)[1]]
    assert other_sizes == ids  # independent of the page size


def test_identical_titles_are_ordered_by_id_so_pages_never_overlap(client, application):
    seed_library(client, application)
    _, items = walk(client, q="same title", page_size=7)  # 30 identical titles over 5 pages
    ids = [hex_id(item["id"]) for item in items]
    assert len(ids) == len(set(ids)) == 30
    assert ids == sorted(ids)


def test_searching_finds_a_book_outside_the_first_50_results(client, application):
    seed_library(client, application)
    _, everything = walk(client)
    position = next(i for i, b in enumerate(everything) if b["title"] == "Zz Last 3")
    assert position >= 200  # nowhere near the first page
    found = get_page(client, q="zz last 3")
    assert [b["title"] for b in found["items"]] == ["Zz Last 3"]
    assert (found["total"], found["page"], found["total_pages"]) == (1, 1, 1)
    # searching spans the whole library, then paginates the matches
    first, matches = walk(client, q="alpha")
    assert (first["total"], first["total_pages"]) == (100, 2)
    assert sorted(b["title"] for b in matches) == [f"Alpha {n:03d}" for n in range(100)]
    assert get_page(client, q="Beta Press")["total"] == 100  # publisher
    assert get_page(client, q="twin")["total"] == 30  # author
    assert get_page(client, q="9780000000012")["total"] == 1  # isbn
    nothing = get_page(client, q="no such book")
    assert (nothing["total"], nothing["total_pages"], nothing["page"], nothing["items"]) == (
        0,
        0,
        1,
        [],
    )


def test_sorting_orders_the_whole_library_not_just_one_page(client, application):
    seed_library(client, application)
    books = database_books(application)
    assert get_page(client, sort="title_desc")["items"][0]["title"] == "Zz Last 6"
    assert get_page(client, sort="title")["items"][0]["title"] == "Alpha 000"
    newest = max(b.created_at for b in books)
    assert get_page(client, sort="recent")["items"][0]["title"].startswith("Beta 09")
    assert max(b.created_at for b in books) == newest
    oldest_year = min(b.publication_year for b in books if b.publication_year)
    youngest_year = max(b.publication_year for b in books if b.publication_year)
    assert get_page(client, sort="year_asc")["items"][0]["publication_year"] == oldest_year
    assert get_page(client, sort="year_desc")["items"][0]["publication_year"] == youngest_year
    last = get_page(client, sort="year_asc", page=5)["items"][-1]
    assert last["publication_year"] is None  # unknown years always go last
    sorted_search = get_page(client, q="alpha", sort="year_desc")["items"]
    assert [b["publication_year"] for b in sorted_search][:5] == [1919] * 5


def test_an_out_of_range_page_returns_the_last_page(client, application):
    seed_library(client, application)
    beyond = get_page(client, page=99)
    assert beyond["page"] == 5 and len(beyond["items"]) == 37 and beyond["total_pages"] == 5
    assert get_page(client, page=99, q="zz last")["page"] == 1


def test_note_counts_ride_along_with_each_page_item(client, application):
    seed_library(client, application)
    first = get_page(client)["items"][0]
    assert first["title"] == "Alpha 000" and first["note_count"] == 3
    assert all(item["note_count"] == 0 for item in get_page(client)["items"][1:])


def test_only_your_own_books_are_listed_and_counted(client, application):
    foreign = seed_library(client, application)
    _, items = walk(client)
    assert len(items) == 237 and not any(i["title"].startswith("Foreign") for i in items)
    assert get_page(client, q="foreign")["total"] == 0
    with application.state.session_factory() as db:
        assert (
            db.scalar(select(func.count()).select_from(Book).where(Book.user_id == foreign)) == 20
        )


def test_listing_pages_never_modifies_any_book(client, application):
    seed_library(client, application)
    before = fingerprint(application)
    for sort in ("title", "recent", "year_asc"):
        walk(client, sort=sort, page_size=20)
    walk(client, q="alpha")
    assert fingerprint(application) == before == (before[0], 257)


def test_an_import_larger_than_the_old_200_limit_is_fully_reachable(client, application):
    columns = ["Book Id", "Title", "Author", "ISBN13"]
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(columns)
    for number in range(230):
        body = f"978{number:09d}"
        check = (10 - sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(body)) % 10) % 10
        writer.writerow(
            [
                str(5000 + number),
                f"Imported {number:03d}",
                f"Author {number % 13}",
                body + str(check),
            ]
        )
    previewed = client.post(
        "/api/books/import/preview",
        content=out.getvalue().encode(),
        headers={"Content-Type": "text/csv"},
    ).json()
    assert previewed["counts"]["to_add"] == 230
    assert (
        client.post("/api/books/import/confirm", json={"token": previewed["token"]}).json()[
            "summary"
        ]["added"]
        == 230
    )
    first, items = walk(client, page_size=100)
    assert (first["total"], first["total_pages"]) == (230, 3)
    assert len({item["id"] for item in items}) == 230 > 200  # nothing is cut off at 200
    assert get_page(client, q="imported 229")["total"] == 1  # the very last one is findable
