# ruff: noqa: E501
"""Scheduled prayer reminder dispatcher: one bounded pass, suitable for a Railway cron job.

Run as ``python -m app.jobs.dispatch_prayer_notifications`` — independent of the web process (no
FastAPI, no Uvicorn, no resident loop). Each invocation reads the clock, finds Rule of Life
occurrences due inside the expiry window, writes one durable ``PushDeliveryAttempt`` per
(occurrence, subscription), claims each with a bounded lease, sends, records the outcome and
exits. It refuses to send anything unless PUSH_DELIVERY_ENABLED=true and VAPID keys are set.

Timing: a reminder fires on the first invocation after its UTC instant, so accuracy equals the
cron cadence (every 5 minutes ⇒ at most ~5 minutes late, never early). A reminder older than
``push_reminder_expiry_minutes`` is marked expired rather than delivered stale. Delivery is
at-least-once under retries, deduplicated on the device by the notification tag; acceptance by
the push service is not proof the device displayed anything.

Recurrence and timezones reuse the Rule of Life service itself (``occurs_on``/``instant``), so
daylight saving follows each entry's own IANA zone: a local time skipped by spring-forward moves
forward with the zone's rules, and a repeated fall-back hour resolves to its first occurrence —
either way one UTC instant, and the unique attempt row makes a second send for the same
occurrence impossible.
"""

import json
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..core.config import Settings
from ..db import utcnow
from ..models import (
    PushDeliveryAttempt,
    PushSubscription,
    RuleOfLifeEntry,
    RuleOfLifeOccurrence,
)
from ..services.rule_of_life import instant, link_for, occurs_on

TEMPORARY = "temporary"   # worth retrying: 429, 5xx, network trouble
GONE = "gone"             # 404/410: the subscription no longer exists at the push service


class WebPushSender:
    """Sends one encrypted Web Push message via pywebpush. Returns the service's status code."""

    def __init__(self, settings: Settings):
        self._private_key = settings.vapid_private_key.get_secret_value()
        self._subject = settings.vapid_subject or "mailto:unset@example.org"

    def __call__(self, subscription_info: dict, payload: str, ttl: int) -> int:
        from pywebpush import WebPushException, webpush

        try:
            response = webpush(
                subscription_info=subscription_info, data=payload, ttl=ttl,
                vapid_private_key=self._private_key, vapid_claims={"sub": self._subject},
            )
            return response.status_code
        except WebPushException as exc:
            if exc.response is not None:
                return exc.response.status_code
            raise


def payload_for(entry: RuleOfLifeEntry, attempt: PushDeliveryAttempt) -> str:
    """Compact and non-sensitive: the prayer's name, a dedup tag and an internal route built only
    from our own data (an Office hour opens on the occurrence's own date). Never a user note,
    token or key."""
    return json.dumps({
        "title": entry.title,
        "body": f"Scheduled for {entry.local_time:%H:%M}",
        "tag": f"rule:{entry.id}:{attempt.occurrence_date.isoformat()}",
        "url": link_for(entry, attempt.occurrence_date),
    })


def seed_due_attempts(db: Session, settings: Settings, now: datetime) -> int:
    """One durable attempt per (due occurrence, live subscription). The unique constraint plus
    ``ON CONFLICT DO NOTHING`` make overlapping invocations collide harmlessly instead of racing
    a SELECT-then-INSERT."""
    expiry = timedelta(minutes=settings.push_reminder_expiry_minutes)
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    seeded = 0
    entries = db.scalars(select(RuleOfLifeEntry).where(RuleOfLifeEntry.active.is_(True), RuleOfLifeEntry.notify.is_(True)))
    for entry in entries:
        subscriptions = db.scalars(select(PushSubscription.id).where(
            PushSubscription.user_id == entry.user_id, PushSubscription.revoked_at.is_(None))).all()
        if not subscriptions:
            continue
        # The expiry window spans at most two local dates in the entry's zone.
        for day in {(now - expiry).astimezone(_zone(entry)).date(), now.astimezone(_zone(entry)).date()}:
            if not occurs_on(entry, day):
                continue
            due = instant(entry, day)
            if not (now - expiry <= due <= now):
                continue
            marked = db.scalar(select(RuleOfLifeOccurrence.id).where(
                RuleOfLifeOccurrence.entry_id == entry.id, RuleOfLifeOccurrence.occurrence_date == day))
            if marked:
                continue
            for subscription_id in subscriptions:
                result = db.execute(
                    insert(PushDeliveryAttempt).values(
                        id=uuid4(), user_id=entry.user_id, entry_id=entry.id, subscription_id=subscription_id,
                        occurrence_date=day, due_at=due, status="pending", attempt_count=0,
                        created_at=now, updated_at=now,
                    ).on_conflict_do_nothing(index_elements=["entry_id", "occurrence_date", "subscription_id"])
                )
                seeded += result.rowcount or 0
    return seeded


def _zone(entry: RuleOfLifeEntry):
    return ZoneInfo(entry.timezone)


def expire_stale(db: Session, settings: Settings, now: datetime) -> int:
    """A reminder past its window is marked expired, never sent hours late."""
    cutoff = now - timedelta(minutes=settings.push_reminder_expiry_minutes)
    result = db.execute(update(PushDeliveryAttempt).where(
        PushDeliveryAttempt.status == "pending", PushDeliveryAttempt.due_at < cutoff,
        or_(PushDeliveryAttempt.claimed_until.is_(None), PushDeliveryAttempt.claimed_until < now),
    ).values(status="expired", updated_at=now))
    return result.rowcount or 0


def claim(db: Session, settings: Settings, attempt_id, now: datetime) -> bool:
    """Atomic lease: exactly one worker wins this UPDATE; a crashed owner's lease simply lapses."""
    lease = timedelta(seconds=settings.push_claim_lease_seconds)
    result = db.execute(update(PushDeliveryAttempt).where(
        PushDeliveryAttempt.id == attempt_id, PushDeliveryAttempt.status == "pending",
        PushDeliveryAttempt.attempt_count < settings.push_max_attempts,
        or_(PushDeliveryAttempt.claimed_until.is_(None), PushDeliveryAttempt.claimed_until < now),
    ).values(claimed_until=now + lease, attempt_count=PushDeliveryAttempt.attempt_count + 1, updated_at=now))
    return (result.rowcount or 0) == 1


def run(session_factory, settings: Settings, sender, now: datetime | None = None) -> dict:
    """One bounded dispatch pass. Returns a count summary (no endpoints, keys or payloads)."""
    if not settings.push_delivery_enabled:
        return {"skipped": "PUSH_DELIVERY_ENABLED is false; nothing sent"}
    if not settings.push_configured:
        return {"skipped": "VAPID keys are not configured; nothing sent"}
    now = now or utcnow()
    summary = {"seeded": 0, "expired": 0, "delivered": 0, "retried": 0, "failed": 0, "revoked_subscriptions": 0, "skipped_marked_or_paused": 0}

    with session_factory.begin() as db:
        summary["expired"] = expire_stale(db, settings, now)
        summary["seeded"] = seed_due_attempts(db, settings, now)

    with session_factory() as db:
        candidates = db.scalars(select(PushDeliveryAttempt.id).where(
            PushDeliveryAttempt.status == "pending", PushDeliveryAttempt.due_at <= now,
            PushDeliveryAttempt.attempt_count < settings.push_max_attempts,
            or_(PushDeliveryAttempt.claimed_until.is_(None), PushDeliveryAttempt.claimed_until < now),
        ).order_by(PushDeliveryAttempt.due_at)).all()

    for attempt_id in candidates:
        # Claim in one short transaction; the network request happens with no transaction open.
        with session_factory.begin() as db:
            if not claim(db, settings, attempt_id, now):
                continue
            attempt = db.get(PushDeliveryAttempt, attempt_id)
            entry = db.get(RuleOfLifeEntry, attempt.entry_id)
            subscription = db.get(PushSubscription, attempt.subscription_id)
            marked = db.scalar(select(RuleOfLifeOccurrence.id).where(
                RuleOfLifeOccurrence.entry_id == attempt.entry_id,
                RuleOfLifeOccurrence.occurrence_date == attempt.occurrence_date))
            if entry is None or not entry.active or not entry.notify or marked or subscription is None or subscription.revoked_at is not None:
                attempt.status, attempt.last_error, attempt.claimed_until = "expired", "no longer eligible at send time", None
                summary["skipped_marked_or_paused"] += 1
                continue
            payload = payload_for(entry, attempt)
            subscription_info = {"endpoint": subscription.endpoint, "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth}}
            attempt_count = attempt.attempt_count

        ttl = settings.push_reminder_expiry_minutes * 60
        try:
            status_code = sender(subscription_info, payload, ttl)
            failure = None if 200 <= status_code < 300 else (GONE if status_code in (404, 410) else TEMPORARY)
            error = None if failure is None else f"push service answered {status_code}"
        except Exception as exc:  # an ambiguous network failure: the push may or may not have left
            failure, error = TEMPORARY, f"network error: {type(exc).__name__}"

        with session_factory.begin() as db:
            attempt = db.get(PushDeliveryAttempt, attempt_id)
            attempt.updated_at = utcnow()
            if failure is None:
                attempt.status, attempt.claimed_until, attempt.last_error = "delivered", None, None
                summary["delivered"] += 1
            elif failure == GONE:
                attempt.status, attempt.claimed_until, attempt.last_error = "failed", None, error
                subscription = db.get(PushSubscription, attempt.subscription_id)
                if subscription is not None and subscription.revoked_at is None:
                    subscription.revoked_at = utcnow()
                    subscription.failure_count += 1
                    subscription.last_failure_at = utcnow()
                    summary["revoked_subscriptions"] += 1
                summary["failed"] += 1
            elif attempt_count >= settings.push_max_attempts:
                attempt.status, attempt.claimed_until, attempt.last_error = "failed", None, f"{error} (retries exhausted)"
                summary["failed"] += 1
            else:
                # Still pending; the lease doubles as exponential backoff until the next run.
                backoff = timedelta(seconds=settings.push_claim_lease_seconds * (2 ** (attempt_count - 1)))
                attempt.claimed_until, attempt.last_error = now + backoff, error
                summary["retried"] += 1
    return summary


def main() -> None:
    from ..db import make_engine, make_session_factory

    settings = Settings()  # the same environment-driven configuration as the API: no hardcoded URLs
    engine = make_engine(
        settings.database_url,
        settings.postgres_password.get_secret_value() if settings.postgres_password else None,
    )
    try:
        sender = WebPushSender(settings) if settings.push_configured else _refuse
        print(run(make_session_factory(engine), settings, sender))
    finally:
        engine.dispose()


def _refuse(*_args, **_kwargs):
    raise RuntimeError("push is not configured")


if __name__ == "__main__":
    main()
