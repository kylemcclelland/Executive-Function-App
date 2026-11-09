"""Server-side verification of Clerk session tokens.

Follows Clerk's documented Python/FastAPI integration (``clerk-backend-api``'s
``authenticate_request``). Identity comes only from the verified token's ``sub`` claim; nothing the
client sends in a body, query string or custom header is ever treated as an identity.
"""

import logging
from collections.abc import Callable
from types import SimpleNamespace

from clerk_backend_api.security import AuthenticateRequestOptions, authenticate_request
from clerk_backend_api.security.types import TokenVerificationErrorReason
from fastapi import HTTPException, Request

from .config import Settings

logger = logging.getLogger("app.auth")

# Resolves a request to a verified Clerk user id, or raises HTTPException.
Authenticator = Callable[[Request], str]

# Failures that are Clerk/network trouble rather than a bad credential: tell the client to retry.
_UNAVAILABLE = {
    TokenVerificationErrorReason.JWK_FAILED_TO_LOAD,
    TokenVerificationErrorReason.SERVER_ERROR,
    TokenVerificationErrorReason.SECRET_KEY_MISSING,
}


def unauthorized() -> HTTPException:
    return HTTPException(
        401, "Authentication required", headers={"WWW-Authenticate": "Bearer"},
    )


class ClerkAuthenticator:
    def __init__(self, settings: Settings):
        self.options = AuthenticateRequestOptions(
            secret_key=(
                settings.clerk_secret_key.get_secret_value() if settings.clerk_secret_key else None
            ),
            jwt_key=settings.clerk_jwt_key,
            authorized_parties=settings.authorized_parties,
            # Browser sessions only: never accept API keys or machine/OAuth tokens as a user.
            accepts_token=["session_token"],
        )

    def __call__(self, request: Request) -> str:
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        token = token.strip()
        if scheme.lower() != "bearer" or not token:
            raise unauthorized()
        # Hand Clerk a view with only the bearer token, so a `__session` cookie is never
        # consulted: cookie credentials would make every endpoint CSRF-able.
        try:
            state = authenticate_request(
                SimpleNamespace(headers={"Authorization": f"Bearer {token}"}), self.options,
            )
        except Exception as exc:  # Fail closed on anything unexpected, never open.
            logger.exception("Session token verification failed unexpectedly")
            raise HTTPException(503, "Authentication is temporarily unavailable") from exc
        if not state.is_signed_in or state.payload is None:
            logger.info("Rejected session token: %s", state.reason and state.reason.value[0])
            if state.reason in _UNAVAILABLE:
                raise HTTPException(503, "Authentication is temporarily unavailable")
            raise unauthorized()
        claims = state.payload
        subject = claims.get("sub")
        # `sts: pending` is a session that still has sign-in tasks to finish (e.g. MFA setup).
        if (
            claims.get("sts") == "pending"
            or not isinstance(subject, str)
            or not subject.startswith("user_")
            or len(subject) > 255
        ):
            raise unauthorized()
        return subject
