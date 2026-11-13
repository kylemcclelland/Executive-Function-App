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
    # The Divine Office is computed by a local checkout of Divinum Officium (https://github.com/DivinumOfficium/divinum-officium).
    # Unset: the Office reports itself unavailable; nothing is composed without the engine.
    divinum_officium_path: str | None = None
    divinum_officium_perl: str = "perl"
    divinum_officium_perl5lib: str | None = None
    # Web Push (VAPID), both base64url: the application-server keypair browsers subscribe against.
    # The private key lives only in this environment variable; it is never stored or logged.
    vapid_public_key: str | None = None
    vapid_private_key: SecretStr | None = None
    # Contact URI (mailto: or https:) a push service may use to reach the operator.
    vapid_subject: str | None = None
    # The master switch for the scheduled-reminder dispatcher. Off by default everywhere: a live
    # sender becomes operational only by deliberately setting PUSH_DELIVERY_ENABLED=true.
    push_delivery_enabled: bool = False
    # A reminder older than this is never sent late; its attempt is marked expired instead.
    push_reminder_expiry_minutes: int = 30
    # How long one dispatcher run owns a claimed attempt (also the base of the retry backoff).
    push_claim_lease_seconds: int = 120
    # Temporary failures (429/5xx/network) are retried at most this many times.
    push_max_attempts: int = 5
    # The verified Clerk user id (`sub`, "user_...") of the application's owner: the only account
    # allowed to use the editorial dashboard. Unset means nobody — editorial access stays closed
    # until the owner is deliberately configured. Never an email, never the first user to sign up.
    owner_clerk_user_id: str | None = None
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
        "google_token_encryption_key", "vapid_public_key", "vapid_private_key", "vapid_subject",
        "owner_clerk_user_id", mode="before",
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
    def push_configured(self) -> bool:
        """Browsers can subscribe. Delivery additionally needs the Phase 2 sender."""
        return bool(self.vapid_public_key and self.vapid_private_key)

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
