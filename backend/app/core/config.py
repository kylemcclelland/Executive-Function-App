import json
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
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
    dev_user_id: UUID | None = None
    dev_user_timezone: str = Field(
        default="UTC", validation_alias=AliasChoices("USER_TIMEZONE", "DEV_USER_TIMEZONE"),
    )
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5173", "http://127.0.0.1:5173",
    ]

    @field_validator("cors_origins", mode="before")
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

    @model_validator(mode="after")
    def guard_development_identity(self):
        if self.app_env not in {"development", "test"} and self.dev_user_id is not None:
            raise ValueError("DEV_USER_ID is forbidden outside development/test")
        return self
