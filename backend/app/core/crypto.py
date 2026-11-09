"""Authenticated encryption for secrets stored in the database (OAuth refresh tokens)."""

from cryptography.fernet import Fernet, InvalidToken, MultiFernet


class TokenCipher:
    """Fernet (AES-128-CBC + HMAC-SHA256). Accepts several comma-separated keys, newest first:
    new values use the first key, and any listed key can still decrypt, so keys can be rotated."""

    def __init__(self, keys: str):
        try:
            fernets = [Fernet(key.strip().encode()) for key in keys.split(",") if key.strip()]
        except (ValueError, TypeError) as exc:
            raise ValueError(
                "GOOGLE_TOKEN_ENCRYPTION_KEY must be Fernet key(s): 32 url-safe base64 bytes"
            ) from exc
        if not fernets:
            raise ValueError("GOOGLE_TOKEN_ENCRYPTION_KEY is empty")
        self._fernet = MultiFernet(fernets)

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str | None:
        """The plaintext, or None if the value was not produced by one of our keys."""
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken:
            return None
