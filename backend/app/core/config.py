import json
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import make_url

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
    # Devotional content is approved by hand. Nobody holds either role unless their verified Clerk
    # user id is listed here, so no user, however signed in, can edit or approve content by default.
    # Editors enter and verify sourced content; approvers approve and publish it. Never settable
    # through the API.
    editor_clerk_user_ids: Annotated[list[str], NoDecode] = []
    approver_clerk_user_ids: Annotated[list[str], NoDecode] = []

    @field_validator(
        "cors_origins", "clerk_authorized_parties", "editor_clerk_user_ids",
        "approver_clerk_user_ids", mode="before",
    )
    @classmethod
    def parse_origins(cls, value):
        if isinstance(value, str):
            if value.lstrip().startswith("["):
                return json.loads(value)
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("editor_clerk_user_ids", "approver_clerk_user_ids")
    @classmethod
    def clerk_user_ids(cls, value: list[str]) -> list[str]:
        if bad := [item for item in value if not item.startswith("user_")]:
            raise ValueError(f"not Clerk user ids (expected user_...): {bad}")
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

    def production_problems(self) -> list[str]:
        """Everything that makes this configuration unsafe to serve real traffic with.

        Checked at startup when APP_ENV=production, which then refuses to start. Each message names
        the setting to fix, never a secret value.
        """
        problems: list[str] = []
        try:
            database = make_url(self.database_url)
        except Exception:
            return ["DATABASE_URL is not a valid database URL"]
        if database.get_backend_name() != "postgresql":
            problems.append("DATABASE_URL must be PostgreSQL (SQLite is for local development)")
        else:
            host = database.host or ""
            private = host in {"localhost", "127.0.0.1"} or host.endswith(".railway.internal")
            secure = database.query.get("sslmode") in {"require", "verify-ca", "verify-full"}
            if not private and not secure:
                problems.append("DATABASE_URL must include ?sslmode=require (database is remote)")
        if not self.clerk_configured:
            problems.append("CLERK_SECRET_KEY (or CLERK_JWT_KEY) is not set")
        if not self.clerk_authorized_parties:
            problems.append("CLERK_AUTHORIZED_PARTIES must list the production origin(s)")
        origins = [*self.authorized_parties, *self.cors_origins, self.frontend_url]
        google = (
            self.google_client_id, self.google_client_secret, self.google_token_encryption_key,
        )
        if self.google_configured:
            origins.append(self.google_redirect_uri)
        elif any(google):
            problems.append(
                "GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET and GOOGLE_TOKEN_ENCRYPTION_KEY "
                "must be set together"
            )
        for origin in origins:
            if "*" in origin:
                problems.append(f"wildcard origins are not allowed ({origin})")
            elif not origin.startswith("https://") or any(
                local in origin for local in ("localhost", "127.0.0.1", "0.0.0.0")
            ):
                problems.append(f"production origins must be https and not local ({origin})")
        return list(dict.fromkeys(problems))
