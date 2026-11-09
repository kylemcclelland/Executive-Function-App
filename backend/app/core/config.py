import json
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Owner of all data created before Clerk authentication. No Clerk account is linked to it
# until the owner explicitly claims it; see docs/clerk-data-migration-plan.md.
LEGACY_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_ROOT.parent / ".env", BACKEND_ROOT / ".env"),
        extra="ignore",
        populate_by_name=True,
    )

    app_env: Literal["development", "test", "production"] = "production"
    database_url: str = "postgresql+psycopg://localhost:5432/executive"
    postgres_password: SecretStr | None = None
    # Clerk session-token verification. Provide the secret key (keys fetched from Clerk and
    # cached) and/or the PEM public key (verified without any network call).
    clerk_secret_key: SecretStr | None = None
    clerk_jwt_key: str | None = None
    # Origins allowed in the token's `azp` claim; defaults to CORS_ORIGINS.
    clerk_authorized_parties: Annotated[list[str] | None, NoDecode] = None
    dev_user_timezone: str = Field(
        default="UTC", validation_alias=AliasChoices("USER_TIMEZONE", "DEV_USER_TIMEZONE"),
    )
    # Google Calendar (OAuth 2.0 web-application flow). All three of the id, secret and encryption
    # key are required for the integration to be offered; otherwise Studium simply works without it.
    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    # Fernet key(s), comma-separated, newest first, used to encrypt refresh tokens at rest.
    google_token_encryption_key: SecretStr | None = None
    # Must exactly match an "Authorized redirect URI" on the Google OAuth client.
    google_redirect_uri: str = "http://localhost:5173/api/integrations/google-calendar/callback"
    # Where the browser is sent after the callback; the only place the backend ever redirects to.
    frontend_url: str = "http://localhost:5173"
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5173", "http://127.0.0.1:5173",
    ]

    @field_validator("cors_origins", "clerk_authorized_parties", mode="before")
    @classmethod
    def parse_origins(cls, value):
        if isinstance(value, str):
            if value.lstrip().startswith("["):
                return json.loads(value)
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("dev_user_timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Unknown IANA timezone") from exc
        return value

    @field_validator(
        "clerk_secret_key", "clerk_jwt_key", "google_client_id", "google_client_secret",
        "google_token_encryption_key", mode="before",
    )
    @classmethod
    def blank_is_unset(cls, value):
        # An empty `CLERK_SECRET_KEY=` line in .env means "not configured", not "empty key".
        if isinstance(value, SecretStr):
            value = value.get_secret_value()
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("google_token_encryption_key")
    @classmethod
    def valid_encryption_key(cls, value):
        if value is not None:
            from .crypto import TokenCipher

            TokenCipher(value.get_secret_value())  # raises ValueError for a malformed key
        return value

    @property
    def google_configured(self) -> bool:
        return bool(
            self.google_client_id and self.google_client_secret and self.google_token_encryption_key
        )

    @property
    def clerk_configured(self) -> bool:
        return self.clerk_secret_key is not None or self.clerk_jwt_key is not None

    @property
    def authorized_parties(self) -> list[str]:
        return self.clerk_authorized_parties or self.cors_origins
