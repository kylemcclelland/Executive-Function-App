from types import SimpleNamespace

from sqlalchemy.engine import URL

from app.core.config import Settings
from app.db import make_engine


def test_postgres_connection_password_fallback(monkeypatch):
    import app.db as db_module
    captured = {}

    def create_engine(url, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    monkeypatch.setattr(db_module, "create_engine", create_engine)
    make_engine("postgresql+psycopg://user@localhost/database", "test-value")
    assert captured["connect_args"] == {"password": "test-value"}
    captured.clear()
    explicit_url = URL.create(
        "postgresql+psycopg", "user", "explicit-value", "localhost", database="database",
    )
    make_engine(explicit_url.render_as_string(hide_password=False), "test-value")
    assert "connect_args" not in captured


def test_environment_password_is_secret(monkeypatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "test-value")
    settings = Settings(app_env="test", _env_file=None)
    assert settings.postgres_password.get_secret_value() == "test-value"
    assert "test-value" not in str(settings)
