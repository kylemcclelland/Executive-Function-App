# ruff: noqa: E501
"""The scheduled reminder dispatcher: due-occurrence selection across timezones and DST, the
feature flag, durable at-least-once claims under concurrency, retries, revocation and expiry.
All clocks are controlled; all push-service traffic is a fake sender — nothing real is sent."""

from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4

from pydantic import SecretStr
from pytest import fixture
from sqlalchemy import select

from app.jobs.dispatch_prayer_notifications import run
from app.models import (
    PushDeliveryAttempt,
    PushSubscription,
    RuleOfLifeEntry,
    RuleOfLifeOccurrence,
    User,
)

WINTER_NOW = datetime(2026, 1, 11, 2, 3, tzinfo=UTC)    # 2026-01-10 21:03 in New York (EST)
SUMMER_NOW = datetime(2026, 7, 11, 1, 3, tzinfo=UTC)    # 2026-07-10 21:03 in New York (EDT)


class FakeSender:
    """Records every send; answers a programmable status code or raises. No network."""

    def __init__(self, status=201):
        self.status, self.raising, self.sent = status, None, []

    def __call__(self, subscription_info, payload, ttl):
        if self.raising:
            raise self.raising
        self.sent.append((subscription_info["endpoint"], payload, ttl))
        return self.status


@fixture
def push_settings(application):
    s = application.state.settings
    s.vapid_public_key, s.vapid_private_key = "test-public-key", SecretStr("test-private-key")
    s.vapid_subject, s.push_delivery_enabled = "mailto:test@example.org", True
    return s


def setup(application, *, local_time=time(21, 0), tz="America/New_York", recurrence="daily",
          weekdays=(), start=date(2026, 1, 1), notify=True, active=True, subscriptions=1, title="Compline"):
    with application.state.session_factory.begin() as db:
        user = User(id=uuid4(), timezone="UTC", clerk_user_id=f"user_{uuid4().hex}")
        db.add(user)
        db.flush()
        entry = RuleOfLifeEntry(user_id=user.id, kind="office_hour", ref="compline", title=title,
                                local_time=local_time, timezone=tz, recurrence=recurrence, weekdays=list(weekdays),
                                start_date=start, notify=notify, active=active, fingerprint=uuid4().hex)
        db.add(entry)
        subs = [PushSubscription(user_id=user.id, endpoint=f"https://push.example.com/{uuid4().hex}",
                                 endpoint_hash=uuid4().hex, p256dh="BKey", auth="auth") for _ in range(subscriptions)]
        db.add_all(subs)
        db.flush()
        return user.id, entry.id, [s.id for s in subs]


def attempts(application):
    with application.state.session_factory() as db:
        return [(a.status, a.attempt_count, a.occurrence_date) for a in db.scalars(select(PushDeliveryAttempt))]


def test_daily_compline_in_standard_time(application, push_settings):
    _, entry_id, _ = setup(application)
    sender = FakeSender()
    summary = run(application.state.session_factory, push_settings, sender, now=WINTER_NOW)
    assert summary["seeded"] == 1 and summary["delivered"] == 1
    endpoint, payload, ttl = sender.sent[0]
    assert '"title": "Compline"' in payload
    assert f'"tag": "rule:{entry_id}:2026-01-10"' in payload
    assert '"url": "/divine-office?date=2026-01-10&hour=compline"' in payload   # the occurrence's own liturgical date, same-origin path
    assert ttl == push_settings.push_reminder_expiry_minutes * 60
    assert attempts(application) == [("delivered", 1, date(2026, 1, 10))]


def test_the_same_reminder_in_daylight_time(application, push_settings):
    setup(application, start=date(2026, 7, 1))
    sender = FakeSender()
    # 21:00 EDT is 01:00 UTC the next day; five minutes earlier (before the due instant) nothing is due.
    early = run(application.state.session_factory, push_settings, sender, now=SUMMER_NOW - timedelta(minutes=8))
    assert early["seeded"] == 0 and sender.sent == []
    assert run(application.state.session_factory, push_settings, sender, now=SUMMER_NOW)["delivered"] == 1


def test_once_and_weekly_recurrences(application, push_settings):
    setup(application, recurrence="once", start=date(2026, 1, 10), title="Once")
    setup(application, recurrence="weekly", weekdays=[5], title="Weekly")        # Saturday; 2026-01-10 is one
    setup(application, recurrence="weekly", weekdays=[2], title="WrongDay")      # Wednesday: not due
    sender = FakeSender()
    assert run(application.state.session_factory, push_settings, sender, now=WINTER_NOW)["delivered"] == 2
    titles = ",".join(payload for _, payload, _ in sender.sent)
    assert "Once" in titles and "Weekly" in titles and "WrongDay" not in titles
    # The one-time prayer never fires again.
    assert run(application.state.session_factory, push_settings, sender, now=WINTER_NOW + timedelta(days=7))["seeded"] == 1  # only the weekly reseeds


def test_spring_forward_skipped_local_time_fires_once(application, push_settings):
    setup(application, local_time=time(2, 30), start=date(2026, 3, 1))
    sender = FakeSender()
    # 02:30 on 2026-03-08 does not exist in New York; the zone's rules carry it to 07:30 UTC.
    now = datetime(2026, 3, 8, 7, 35, tzinfo=UTC)
    assert run(application.state.session_factory, push_settings, sender, now=now)["delivered"] == 1
    assert run(application.state.session_factory, push_settings, sender, now=now + timedelta(minutes=10))["delivered"] == 0
    assert len(sender.sent) == 1


def test_fall_back_repeated_local_hour_fires_once(application, push_settings):
    setup(application, local_time=time(1, 30), start=date(2026, 10, 1))
    sender = FakeSender()
    # 01:30 on 2026-11-01 happens twice in New York; the first (EDT, 05:30 UTC) is the occurrence.
    first = datetime(2026, 11, 1, 5, 35, tzinfo=UTC)
    assert run(application.state.session_factory, push_settings, sender, now=first)["delivered"] == 1
    # At the second 01:30 (EST, 06:30 UTC) the unique attempt row already exists: nothing is sent again.
    second = datetime(2026, 11, 1, 6, 35, tzinfo=UTC)
    summary = run(application.state.session_factory, push_settings, sender, now=second)
    assert summary["seeded"] == 0 and summary["delivered"] == 0 and len(sender.sent) == 1


def test_paused_notify_off_marked_and_no_subscription_send_nothing(application, push_settings):
    setup(application, active=False)
    setup(application, notify=False)
    setup(application, subscriptions=0)
    _, entry_id, _ = setup(application, title="Marked")
    with application.state.session_factory.begin() as db:
        entry = db.get(RuleOfLifeEntry, entry_id)
        db.add(RuleOfLifeOccurrence(entry_id=entry_id, user_id=entry.user_id, occurrence_date=date(2026, 1, 10), status="completed"))
    sender = FakeSender()
    summary = run(application.state.session_factory, push_settings, sender, now=WINTER_NOW)
    assert summary["seeded"] == 0 and sender.sent == []


def test_pause_or_mark_between_seeding_and_sending(application, push_settings):
    _, entry_id, _ = setup(application)
    sender = FakeSender(status=429)                                              # first run seeds but delivery is refused
    run(application.state.session_factory, push_settings, sender, now=WINTER_NOW)
    with application.state.session_factory.begin() as db:
        db.get(RuleOfLifeEntry, entry_id).active = False
        attempt = db.scalar(select(PushDeliveryAttempt))
        attempt.claimed_until = None                                             # the backoff has passed
    good = FakeSender()
    summary = run(application.state.session_factory, push_settings, good, now=WINTER_NOW + timedelta(minutes=5))
    assert summary["skipped_marked_or_paused"] == 1 and good.sent == []
    assert attempts(application)[0][0] == "expired"


def test_multiple_browsers_each_get_the_reminder(application, push_settings):
    setup(application, subscriptions=2)
    sender = FakeSender()
    summary = run(application.state.session_factory, push_settings, sender, now=WINTER_NOW)
    assert summary["seeded"] == 2 and summary["delivered"] == 2
    assert len({endpoint for endpoint, _, _ in sender.sent}) == 2


def test_cross_user_isolation(application, push_settings):
    setup(application, title="Alices Compline")
    setup(application, title="Bobs Compline")
    sender = FakeSender()
    run(application.state.session_factory, push_settings, sender, now=WINTER_NOW)
    by_endpoint = {endpoint: payload for endpoint, payload, _ in sender.sent}
    assert len(by_endpoint) == 2
    for payload in by_endpoint.values():
        assert ("Alices" in payload) != ("Bobs" in payload)                       # each browser hears only its own user's prayer


def test_gone_subscription_is_revoked_and_never_retried(application, push_settings):
    _, _, (subscription_id,) = setup(application)
    sender = FakeSender(status=410)
    summary = run(application.state.session_factory, push_settings, sender, now=WINTER_NOW)
    assert summary["failed"] == 1 and summary["revoked_subscriptions"] == 1
    with application.state.session_factory() as db:
        assert db.get(PushSubscription, subscription_id).revoked_at is not None
        assert db.scalar(select(PushDeliveryAttempt.last_error)) == "push service answered 410"
    # The next day's occurrence seeds nothing for a revoked subscription.
    assert run(application.state.session_factory, push_settings, FakeSender(), now=WINTER_NOW + timedelta(days=1))["seeded"] == 0


def test_temporary_failures_back_off_then_succeed(application, push_settings):
    setup(application)
    flaky = FakeSender(status=503)
    summary = run(application.state.session_factory, push_settings, flaky, now=WINTER_NOW)
    assert summary["retried"] == 1 and attempts(application)[0][:2] == ("pending", 1)
    # While the backoff lease holds, an immediate second run must not touch it.
    assert run(application.state.session_factory, push_settings, FakeSender(), now=WINTER_NOW + timedelta(seconds=30))["delivered"] == 0
    # After the lease, within the expiry window, it is retried and delivered.
    assert run(application.state.session_factory, push_settings, FakeSender(), now=WINTER_NOW + timedelta(minutes=5))["delivered"] == 1


def test_network_errors_retry_and_eventually_exhaust(application, push_settings):
    setup(application)
    broken = FakeSender()
    broken.raising = ConnectionError("refused")
    now = WINTER_NOW
    for _ in range(push_settings.push_max_attempts):
        run(application.state.session_factory, push_settings, broken, now=now)
        now += timedelta(minutes=5)
        with application.state.session_factory.begin() as db:
            attempt = db.scalar(select(PushDeliveryAttempt))
            attempt.claimed_until = None                                         # fast-forward past the backoff
    status, count, _ = attempts(application)[0]
    assert (status, count) == ("failed", push_settings.push_max_attempts)
    with application.state.session_factory() as db:
        assert "ConnectionError" in db.scalar(select(PushDeliveryAttempt.last_error))


def test_duplicate_invocations_and_concurrent_claims(application, push_settings):
    setup(application)
    sender = FakeSender()
    assert run(application.state.session_factory, push_settings, sender, now=WINTER_NOW)["delivered"] == 1
    # The same minute again: nothing reseeds, nothing resends.
    again = run(application.state.session_factory, push_settings, sender, now=WINTER_NOW)
    assert again["seeded"] == 0 and again["delivered"] == 0 and len(sender.sent) == 1


def test_a_live_lease_blocks_other_workers_and_lapses_after_a_crash(application, push_settings):
    setup(application)
    quiet = FakeSender(status=429)
    run(application.state.session_factory, push_settings, quiet, now=WINTER_NOW)  # leaves a pending attempt
    with application.state.session_factory.begin() as db:
        attempt = db.scalar(select(PushDeliveryAttempt))
        attempt.claimed_until = WINTER_NOW + timedelta(seconds=90)               # another worker holds the lease
    held = run(application.state.session_factory, push_settings, FakeSender(), now=WINTER_NOW + timedelta(seconds=10))
    assert held["delivered"] == 0
    # The owner crashed; once the bounded lease lapses the attempt is claimable again.
    recovered = run(application.state.session_factory, push_settings, FakeSender(), now=WINTER_NOW + timedelta(seconds=120))
    assert recovered["delivered"] == 1


def test_stale_reminders_expire_instead_of_arriving_late(application, push_settings):
    user_id, entry_id, (subscription_id,) = setup(application)
    with application.state.session_factory.begin() as db:
        db.add(PushDeliveryAttempt(user_id=user_id, entry_id=entry_id, subscription_id=subscription_id,
                                   occurrence_date=date(2026, 1, 10), due_at=WINTER_NOW - timedelta(hours=2), status="pending"))
    sender = FakeSender()
    summary = run(application.state.session_factory, push_settings, sender, now=WINTER_NOW + timedelta(hours=1))
    assert summary["expired"] == 1 and sender.sent == []


def test_delivery_flag_defaults_off_and_blocks_everything(application, push_settings):
    setup(application)
    push_settings.push_delivery_enabled = False
    sender = FakeSender()
    summary = run(application.state.session_factory, push_settings, sender, now=WINTER_NOW)
    assert "skipped" in summary and sender.sent == [] and attempts(application) == []


def test_unconfigured_vapid_blocks_dispatch(application, push_settings):
    setup(application)
    push_settings.vapid_private_key = None
    summary = run(application.state.session_factory, push_settings, FakeSender(), now=WINTER_NOW)
    assert "skipped" in summary


def test_migration_0015_round_trip(application):
    from pathlib import Path

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect

    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with application.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        assert "push_delivery_attempts" in inspect(connection).get_table_names()
        assert "revoked_at" in {c["name"] for c in inspect(connection).get_columns("push_subscriptions")}
        command.downgrade(config, "0014")
        assert "push_delivery_attempts" not in inspect(connection).get_table_names()
        assert "revoked_at" not in {c["name"] for c in inspect(connection).get_columns("push_subscriptions")}
        assert "rule_of_life_entries" in inspect(connection).get_table_names()
        command.upgrade(config, "head")
        assert "push_delivery_attempts" in inspect(connection).get_table_names()
