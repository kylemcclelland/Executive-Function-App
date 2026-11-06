from datetime import UTC, datetime

from sqlalchemy import DateTime, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.types import TypeDecorator


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            if value.tzinfo is None:
                raise ValueError("Timestamp must be timezone aware")
            return value.astimezone(UTC)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return value


class Base(DeclarativeBase):
    pass


def make_engine(url: str, postgres_password: str | None = None):
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    parsed = make_url(url)
    if (
        parsed.get_backend_name() == "postgresql"
        and parsed.password is None
        and postgres_password is not None
    ):
        kwargs = {"connect_args": {"password": postgres_password}}
    engine = create_engine(url, pool_pre_ping=True, **kwargs)
    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
    return engine


def make_session_factory(engine):
    return sessionmaker(engine, expire_on_commit=False)
