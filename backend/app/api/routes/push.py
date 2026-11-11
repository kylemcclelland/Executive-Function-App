# ruff: noqa: E501
"""Web Push subscriptions for Rule of Life reminders.

Phase 1: a browser can register and remove its own subscription; nothing is sent yet (there is
no delivery job). The subscription a browser posts is untrusted input: the endpoint must be an
HTTPS URL of sane length and the keys base64url, nothing more is accepted or stored. Every
endpoint here is scoped to the authenticated user; nobody can list, read or delete another
user's subscriptions, and responses never echo endpoints or keys back.
"""

import hashlib
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select

from ...db import utcnow
from ...models import PushSubscription
from ..dependencies import DB, CurrentUser

router = APIRouter(prefix="/api/push", tags=["push"])

B64URL = r"^[A-Za-z0-9_\-=]+$"


def endpoint_hash(endpoint: str) -> str:
    return hashlib.sha256(endpoint.encode()).hexdigest()


class SubscriptionKeys(BaseModel):
    p256dh: Annotated[str, Field(min_length=1, max_length=512, pattern=B64URL)]
    auth: Annotated[str, Field(min_length=1, max_length=512, pattern=B64URL)]


class SubscriptionIn(BaseModel):
    endpoint: Annotated[str, Field(min_length=1, max_length=2000)]
    keys: SubscriptionKeys

    @field_validator("endpoint")
    @classmethod
    def https_endpoint(cls, value: str) -> str:
        # Only what PushManager.subscribe issues: an absolute HTTPS URL, no credentials, no spaces.
        parts = urlsplit(value)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or any(c.isspace() for c in value):
            raise ValueError("Not a push service endpoint")
        return value


class EndpointIn(BaseModel):
    endpoint: Annotated[str, Field(min_length=1, max_length=2000)]


def settings(request: Request):
    return request.app.state.settings


@router.get("/config")
def push_config(request: Request, user: CurrentUser):
    """Public VAPID configuration only; the private key never leaves the server environment."""
    s = settings(request)
    return {"configured": s.push_configured, "public_key": s.vapid_public_key if s.push_configured else None}


@router.get("/status")
def push_status(request: Request, db: DB, user: CurrentUser):
    """Whether push is configured, whether scheduled delivery is switched on, and how many browsers this user has subscribed. Never any endpoint or key, and never another user's anything."""
    s = settings(request)
    count = db.scalar(select(func.count()).select_from(PushSubscription).where(PushSubscription.user_id == user.id, PushSubscription.revoked_at.is_(None)))
    active = s.push_configured and s.push_delivery_enabled
    return {"configured": s.push_configured, "subscription_count": count, "delivery": "active" if active else "pending",
            "detail": "Scheduled reminders are being dispatched." if active else "Subscriptions are registered, but scheduled reminders are not sent yet."}


@router.post("/subscriptions", status_code=201)
def register_subscription(body: SubscriptionIn, request: Request, db: DB, user: CurrentUser):
    """Registers or refreshes this browser's subscription (idempotent per endpoint).

    An endpoint names one browser profile globally, so if it was registered under another
    account that signed in on the same browser, it moves to the current user instead of
    duplicating — the browser belongs to whoever is signed in now.
    """
    if not settings(request).push_configured:
        raise HTTPException(503, "Push notifications are not configured on this server")
    digest = endpoint_hash(body.endpoint)
    existing = db.scalar(select(PushSubscription).where(PushSubscription.endpoint_hash == digest))
    if existing is not None:
        existing.user_id = user.id
        existing.endpoint = body.endpoint
        existing.p256dh, existing.auth = body.keys.p256dh, body.keys.auth
        existing.failure_count, existing.last_failure_at = 0, None
        existing.revoked_at = None  # a fresh registration revives a subscription the push service had reported gone
        existing.updated_at = utcnow()
        db.flush()
        return {"id": str(existing.id), "refreshed": True}
    subscription = PushSubscription(user_id=user.id, endpoint=body.endpoint, endpoint_hash=digest, p256dh=body.keys.p256dh, auth=body.keys.auth)
    db.add(subscription)
    db.flush()
    return {"id": str(subscription.id), "refreshed": False}


@router.delete("/subscriptions", status_code=204)
def remove_subscription(body: EndpointIn, db: DB, user: CurrentUser):
    """Removes this browser's subscription by its endpoint. Only the caller's own rows are reachable; a stranger's endpoint deletes nothing."""
    db.execute(delete(PushSubscription).where(PushSubscription.user_id == user.id, PushSubscription.endpoint_hash == endpoint_hash(body.endpoint)))
    return Response(status_code=204)
