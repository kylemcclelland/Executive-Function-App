# ruff: noqa: E501
"""The owner-only editorial dashboard: closed by default, owner-gated everywhere, draft privacy
across every access path, and the full verify → approve → publish flow with its audit trail.
All mutations run against the per-test temporary database; the real local drafts are untouched."""

from datetime import date
from uuid import uuid4

from clerk_tokens import bearer
from fastapi.testclient import TestClient
from pytest import fixture
from sqlalchemy import select

from app.models import Devotion, DevotionEvent, PrayerText

OWNER, READER = "user_owner_account", "user_ordinary_reader"
GREEK = "Ἅγιος ὁ Θεός, Ἅγιος Ἰσχυρός, Ἅγιος Ἀθάνατος,\nἐλέησον ἡμᾶς."


@fixture
def app_with_owner(application):
    application.state.settings.owner_clerk_user_id = OWNER
    return application


def draft(application, slug="trisagion-prayers", status="proposed"):
    """An imported-style unpublished draft with English and Greek texts, like batch 01 created."""
    with application.state.session_factory.begin() as db:
        devotion = Devotion(id=uuid4(), slug=slug, title="Trisagion", category="Byzantine", estimated_minutes=1,
                            overview="A short history.", status=status, prose_origin="research_import", created_by="import:devotion-library-batch-01",
                            steps=[{"kind": "prayer", "title": None, "instruction": None, "text_slot": "main", "devotion_slug": None, "repeat": None, "section": None, "group": None, "optional": False}],
                            discovery={"tradition": "Byzantine", "theological_themes": ["Trinity"], "duration_min_minutes": 0.3, "duration_max_minutes": 0.8})
        db.add(devotion)
        db.flush()
        texts = [PrayerText(devotion_id=devotion.id, slot="main", language="en", body="Holy God, Holy Mighty, Holy Immortal,\nhave mercy on us.",
                            is_translation=True, source_title="Test source", attribution="Traditional", license_status="public_domain", status="proposed", entered_by="import"),
                 PrayerText(devotion_id=devotion.id, slot="main", language="el", body=GREEK,
                            source_title="Test source", attribution="Traditional", license_status="public_domain", status="proposed", entered_by="import")]
        db.add_all(texts)
        db.flush()
        return str(devotion.id), [str(t.id) for t in texts]


def test_editorial_is_closed_until_an_owner_is_configured(application):
    draft(application)
    client = TestClient(application, headers=bearer(OWNER))      # signed in, but no owner is configured
    for path in ("/api/editorial/access", "/api/editorial/devotions", "/api/editorial/devotions/trisagion-prayers"):
        assert client.get(path).status_code == 403, path


def test_only_the_configured_owner_passes(app_with_owner):
    _, (en_id, _) = draft(app_with_owner)
    anonymous = TestClient(app_with_owner, headers={})
    reader = TestClient(app_with_owner, headers=bearer(READER))
    owner = TestClient(app_with_owner, headers=bearer(OWNER))
    probes = [("GET", "/api/editorial/access"), ("GET", "/api/editorial/devotions"), ("GET", "/api/editorial/devotions/trisagion-prayers"),
              ("POST", "/api/editorial/devotions/trisagion-prayers/verify-source"), ("POST", f"/api/editorial/devotions/trisagion-prayers/texts/{en_id}/verify-source")]
    for method, path in probes:
        assert anonymous.request(method, path).status_code == 401, path
        assert reader.request(method, path).status_code == 403, path           # authenticated is not authorized
    assert owner.get("/api/editorial/access").json() == {"owner": True}
    queue = owner.get("/api/editorial/devotions").json()
    assert queue["summary"]["total"] >= 1 and any(d["slug"] == "trisagion-prayers" for d in queue["devotions"])


def test_unpublished_drafts_are_invisible_to_ordinary_readers_everywhere(app_with_owner):
    draft(app_with_owner)
    reader = TestClient(app_with_owner, headers=bearer(READER))
    assert "trisagion-prayers" not in {d["slug"] for d in reader.get("/api/devotions").json()}
    assert reader.get("/api/devotions/trisagion-prayers").status_code == 404   # direct URL access leaks nothing
    schedule = reader.post("/api/rule-of-life", json={"kind": "devotion", "ref": "trisagion-prayers", "local_time": "08:00",
                                                      "timezone": "UTC", "recurrence": "daily", "start_date": "2026-11-01"})
    assert schedule.status_code == 404                                         # not even its title via scheduling


def test_the_owners_own_seeded_library_stays_visible(app_with_owner):
    with app_with_owner.state.session_factory.begin() as db:
        db.add(Devotion(id=uuid4(), slug="hail-mary", title="Hail Mary", overview="x", status="proposed", prose_origin="ai_draft", created_by="seed:devotion-drafts-v1"))
    reader = TestClient(app_with_owner, headers=bearer(READER))
    assert "hail-mary" in {d["slug"] for d in reader.get("/api/devotions").json()}


def test_full_review_flow_publishes_and_return_hides_again(app_with_owner):
    devotion_id, text_ids = draft(app_with_owner)
    owner = TestClient(app_with_owner, headers=bearer(OWNER))
    reader = TestClient(app_with_owner, headers=bearer(READER))
    base = "/api/editorial/devotions/trisagion-prayers"

    # Out-of-order transitions are refused, and publish requires approved texts.
    assert owner.post(f"{base}/approve").status_code == 409
    assert owner.post(f"{base}/publish").status_code == 409
    assert owner.post(f"{base}/verify-source").status_code == 200
    assert owner.post(f"{base}/approve").status_code == 200
    assert owner.post(f"{base}/publish").status_code == 409                    # texts still unapproved

    for text_id in text_ids:
        assert owner.post(f"{base}/texts/{text_id}/approve").status_code == 409  # a text is verified before approval
        assert owner.post(f"{base}/texts/{text_id}/verify-source").status_code == 200
        assert owner.post(f"{base}/texts/{text_id}/approve").status_code == 200
    published = owner.post(f"{base}/publish")
    assert published.status_code == 200 and published.json()["status"] == "published"

    # Now, and only now, an ordinary reader sees it — with the Greek intact.
    detail = reader.get("/api/devotions/trisagion-prayers")
    assert detail.status_code == 200
    assert next(t["body"] for t in detail.json()["texts"] if t["language"] == "el") == GREEK

    with app_with_owner.state.session_factory() as db:
        actions = [(e.action, e.actor) for e in db.scalars(select(DevotionEvent).order_by(DevotionEvent.created_at))]
        assert ("publish", OWNER) in actions and ("text_verify_source", OWNER) in actions
        assert len(actions) >= 7                                               # every step left an audit event
        devotion = db.get(Devotion, __import__("uuid").UUID(devotion_id))
        assert devotion.approved_by == OWNER and devotion.published_at is not None

    # Returning it for further work withdraws it from readers again.
    assert owner.post(f"{base}/return").status_code == 200
    assert reader.get("/api/devotions/trisagion-prayers").status_code == 404


def test_detail_shows_texts_metadata_and_history_to_the_owner(app_with_owner):
    draft(app_with_owner)
    owner = TestClient(app_with_owner, headers=bearer(OWNER))
    detail = owner.get("/api/editorial/devotions/trisagion-prayers").json()
    assert {t["language"] for t in detail["texts"]} == {"en", "el"}
    assert next(t for t in detail["texts"] if t["language"] == "el")["body"] == GREEK
    assert detail["discovery"]["duration_max_minutes"] == 0.8 and detail["themes"] == ["Trinity"]
    assert detail["tradition"] == "Byzantine" and detail["created_by"] == "import:devotion-library-batch-01"


def test_verification_refuses_a_text_without_cleared_rights(app_with_owner):
    draft(app_with_owner, slug="unverified-prayer")
    with app_with_owner.state.session_factory.begin() as db:
        devotion = db.scalar(select(Devotion).where(Devotion.slug == "unverified-prayer"))
        prayer = devotion.texts[0]
        prayer.license_status = "unverified"
        text_id = str(prayer.id)
    owner = TestClient(app_with_owner, headers=bearer(OWNER))
    refused = owner.post(f"/api/editorial/devotions/unverified-prayer/texts/{text_id}/verify-source")
    assert refused.status_code == 422


def test_rule_of_life_entries_for_legacy_devotions_keep_working(app_with_owner, application=None):
    with app_with_owner.state.session_factory.begin() as db:
        db.add(Devotion(id=uuid4(), slug="the-holy-rosary", title="The Holy Rosary", overview="x", status="proposed", prose_origin="ai_draft", created_by="seed:devotion-drafts-v1"))
    reader = TestClient(app_with_owner, headers=bearer(READER))
    created = reader.post("/api/rule-of-life", json={"kind": "devotion", "ref": "the-holy-rosary", "local_time": "08:00",
                                                     "timezone": "UTC", "recurrence": "daily", "start_date": str(date(2026, 11, 1))})
    assert created.status_code == 201
