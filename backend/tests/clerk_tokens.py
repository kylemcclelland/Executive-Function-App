"""Real RS256 Clerk-shaped session tokens, verified by the production code path in tests."""

import time

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

AUTHORIZED_ORIGIN = "http://localhost:5173"
DEFAULT_SUBJECT = "user_test_default"


def _keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private, public


PRIVATE_KEY, PUBLIC_KEY = _keypair()
OTHER_PRIVATE_KEY, _ = _keypair()


def make_token(subject: str = DEFAULT_SUBJECT, *, key: str = PRIVATE_KEY, **overrides) -> str:
    now = int(time.time())
    claims = {
        "sub": subject, "azp": AUTHORIZED_ORIGIN, "iss": "https://clerk.test", "sid": "sess_test",
        "iat": now, "nbf": now, "exp": now + 60, "v": 2,
    }
    claims.update(overrides)
    claims = {name: value for name, value in claims.items() if value is not None}
    return jwt.encode(claims, key, algorithm="RS256")


def bearer(subject: str = DEFAULT_SUBJECT, **kwargs) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(subject, **kwargs)}"}
