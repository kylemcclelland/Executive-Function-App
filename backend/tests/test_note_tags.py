from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import create_app
from app.models import Note, NoteTag, User


def note(client, title="A note", **kwargs):
    response = client.post("/api/notes", json={"title": title, **kwargs})
    assert response.status_code == 201, response.text
    return response.json()


def suggestions(client, **params):
    response = client.get("/api/notes/tags", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def names(client, **params):
    return [item["tag"] for item in suggestions(client, **params)]


def insert_notes(application, owner: UUID, spec: list[list[str]]):
    """Notes created straight in the database, e.g. to simulate tags saved before this feature."""
    with application.state.session_factory.begin() as db:
        for number, tags in enumerate(spec):
            item = Note(user_id=owner, title=f"Seeded {number}", content="")
            item.tag_rows = [NoteTag(tag=tag) for tag in tags]
            db.add(item)


def my_id(client) -> UUID:
    return UUID(client.get("/api/user").json()["id"])


def stored_tags(application, note_id: str) -> list[str]:
    with application.state.session_factory() as db:
        return sorted(db.scalars(select(NoteTag.tag).where(NoteTag.note_id == UUID(note_id))))


# ------------------------------------------------------------ suggestions from all notes


def test_suggestions_come_from_every_note_with_counts(client):
    note(client, "One", tags=["Ethics", "Telos"])
    note(client, "Two", tags=["Ethics", "Law"])
    note(client, "Three", tags=["Ethics"])
    note(client, "Untagged")
    assert suggestions(client) == [
        {"tag": "Ethics", "count": 3},
        {"tag": "Law", "count": 1},
        {"tag": "Telos", "count": 1},
    ]


def test_suggestions_match_as_you_type_prefix_first_and_ignore_case(client):
    for title, tags in [
        ("a", ["Ethics", "Ethical theory"]),
        ("b", ["Ethics", "Aesthetics"]),
        ("c", ["Metaethics"]),
        ("d", ["Law"]),
    ]:
        note(client, title, tags=tags)
    assert names(client, q="eth") == ["Ethics", "Ethical theory", "Metaethics"]
    assert names(client, q="ETH") == ["Ethics", "Ethical theory", "Metaethics"]
    assert names(client, q="  #eth  ") == ["Ethics", "Ethical theory", "Metaethics"]
    assert "Aesthetics" in names(client, q="thetic")  # substring matches too
    assert names(client, q="zzz") == [] and names(client, q="") == names(client)
    assert names(client, limit=2) == ["Ethics", "Aesthetics"]  # most used, then alphabetical
    assert client.get("/api/notes/tags", params={"limit": 0}).status_code == 422
    assert client.get("/api/notes/tags", params={"limit": 51}).status_code == 422


def test_suggestions_are_empty_without_tags(client):
    assert suggestions(client) == []
    note(client, "No tags")
    assert suggestions(client, q="a") == []


def test_one_suggestion_per_tag_whatever_the_stored_capitalization(client, application):
    insert_notes(application, my_id(client), [["law"], ["law"], ["Law"], ["LAW"]])
    assert suggestions(client) == [{"tag": "law", "count": 4}]  # the most-used spelling wins
    insert_notes(application, my_id(client), [["Zen"], ["zen"]])
    assert suggestions(client, q="zen") == [{"tag": "Zen", "count": 2}]  # a tie is alphabetical


# ------------------------------------------------------------ duplicates and capitalization


def test_new_tags_keep_the_capitalization_typed(client):
    created = note(client, "Fresh", tags=["Thomism", "natural LAW", "ST I-II"])
    assert created["tags"] == ["natural LAW", "ST I-II", "Thomism"]  # case-insensitive order
    assert client.get(f"/api/notes/{created['id']}").json()["tags"] == created["tags"]


def test_duplicates_are_removed_regardless_of_case_and_whitespace(client):
    created = note(
        client, "Dupes", tags=["Ethics", "ethics", "  ETHICS  ", "#Ethics", "e thics", "Ethics "]
    )
    assert created["tags"] == ["e thics", "Ethics"]
    spaced = note(client, "Spacing", tags=["  a   b ", "A B", "a\tb", "   ", "", "#"])
    assert spaced["tags"] == ["a b"]


def test_an_existing_tags_capitalization_is_reused(client, application):
    note(client, "First", tags=["Ethics"])
    second = note(client, "Second", tags=["ethics", "ETHICS "])
    assert second["tags"] == ["Ethics"]  # not "ethics"
    third = note(client, "Third")
    edited = client.patch(
        f"/api/notes/{third['id']}", json={"tags": ["eThIcS", "Metaphysics"]}
    ).json()
    assert edited["tags"] == ["Ethics", "Metaphysics"]
    again = note(client, "Fourth", tags=["metaphysics"])
    assert again["tags"] == ["Metaphysics"]  # new tags become reusable too
    assert suggestions(client, q="ethics") == [{"tag": "Ethics", "count": 3}]
    with application.state.session_factory() as db:
        spellings = set(db.scalars(select(NoteTag.tag).where(func.lower(NoteTag.tag) == "ethics")))
    assert spellings == {"Ethics"}  # no second spelling exists


def test_legacy_lowercase_tags_are_reused_not_duplicated(client, application):
    insert_notes(application, my_id(client), [["law", "ethics"]])
    created = note(client, "New", tags=["Law", "Ethics", "Brand New"])
    assert created["tags"] == ["Brand New", "ethics", "law"]  # existing spellings win
    assert suggestions(client, q="law") == [{"tag": "law", "count": 2}]


def test_a_notes_own_spelling_is_kept_when_it_is_saved_again(client):
    created = note(client, "Mine", tags=["Ethics", "Telos"])
    same = client.patch(
        f"/api/notes/{created['id']}", json={"tags": ["ETHICS", "telos", "Law"]}
    ).json()
    assert same["tags"] == ["Ethics", "Law", "Telos"]
    assert (
        client.patch(f"/api/notes/{created['id']}", json={"title": "Renamed"}).json()["tags"]
        == same["tags"]
    )
    removed = client.patch(f"/api/notes/{created['id']}", json={"tags": ["Law"]}).json()
    assert removed["tags"] == ["Law"]
    assert suggestions(client) == [{"tag": "Law", "count": 1}]  # removed tags stop being suggested


def test_the_tag_limits_still_apply(client):
    long = "x" * 80
    assert note(client, "Long", tags=[long])["tags"] == ["x" * 50]
    many = note(client, "Many", tags=[f"tag {n:02d}" for n in range(30)])
    assert len(many["tags"]) == 20


# ------------------------------------------------------------ users and notes stay separate


def test_tags_belong_to_their_own_notes_and_users(client, application):
    foreign = uuid4()
    with application.state.session_factory.begin() as db:
        db.add(User(id=foreign, timezone="UTC"))
        db.flush()
        theirs = Note(user_id=foreign, title="Theirs", content="")
        theirs.tag_rows = [NoteTag(tag="ETHICS"), NoteTag(tag="Secret Project")]
        db.add(theirs)
        db.flush()
        theirs_id = theirs.id
    mine = note(client, "Mine", tags=["ethics"])
    other = note(client, "Other", tags=["Law"])
    assert mine["tags"] == ["ethics"]  # another user's "ETHICS" is irrelevant
    assert stored_tags(application, mine["id"]) == ["ethics"]
    assert stored_tags(application, other["id"]) == ["Law"]
    assert stored_tags(application, str(theirs_id)) == ["ETHICS", "Secret Project"]  # untouched
    assert names(client) == ["ethics", "Law"]
    assert names(client, q="secret") == []
    assert client.get("/api/notes", params={"tag": "secret project"}).json() == []
    assert [n["id"] for n in client.get("/api/notes", params={"tag": "ETHICS"}).json()] == [
        mine["id"]
    ]


def test_filtering_and_searching_by_tag_ignore_case(client):
    a = note(client, "A", tags=["Ethics"])
    b = note(client, "B", tags=["Natural Law"])
    note(client, "C", tags=["Other"])
    ids = lambda **params: {n["id"] for n in client.get("/api/notes", params=params).json()}  # noqa: E731
    assert ids(tag="ethics") == {a["id"]} == ids(tag="ETHICS") == ids(tag="  #Ethics ")
    assert ids(q="natural law") == {b["id"]} and ids(q="NATURAL") == {b["id"]}
    assert ids(q="ethic") == {a["id"]}


def test_existing_notes_and_their_tags_are_preserved_when_other_notes_change(client, application):
    first = note(client, "First", tags=["Ethics", "Telos"])
    second = note(client, "Second", tags=["ethics"])
    client.patch(f"/api/notes/{second['id']}", json={"tags": []})
    client.delete(f"/api/notes/{second['id']}")
    assert client.get(f"/api/notes/{first['id']}").json()["tags"] == ["Ethics", "Telos"]
    assert stored_tags(application, first["id"]) == ["Ethics", "Telos"]
    assert suggestions(client) == [{"tag": "Ethics", "count": 1}, {"tag": "Telos", "count": 1}]


def test_deleting_a_note_removes_its_tags_from_suggestions(client):
    kept = note(client, "Kept", tags=["Shared"])
    gone = note(client, "Gone", tags=["Shared", "Only Here"])
    assert {"tag": "Shared", "count": 2} in suggestions(client)
    assert client.delete(f"/api/notes/{gone['id']}").status_code == 204
    assert suggestions(client) == [{"tag": "Shared", "count": 1}]
    assert client.get(f"/api/notes/{kept['id']}").json()["tags"] == ["Shared"]


def test_tags_and_suggestions_persist_across_application_instances(client, application):
    created = note(client, "Persistent", tags=["Metaphysics", "Being"])
    with TestClient(create_app(application.state.settings)) as restarted:
        assert restarted.get(f"/api/notes/{created['id']}").json()["tags"] == [
            "Being",
            "Metaphysics",
        ]
        assert names(restarted, q="meta") == ["Metaphysics"]
        reused = restarted.post(
            "/api/notes", json={"title": "After restart", "tags": ["metaphysics"]}
        ).json()
        assert reused["tags"] == ["Metaphysics"]


@pytest.mark.parametrize("payload", [{"tags": "ethics"}, {"tags": [1, 2]}, {"tags": None}])
def test_malformed_tags_are_rejected(client, payload):
    created = note(client, "X", tags=["Keep"])
    assert client.patch(f"/api/notes/{created['id']}", json=payload).status_code == 422
    assert client.get(f"/api/notes/{created['id']}").json()["tags"] == ["Keep"]
