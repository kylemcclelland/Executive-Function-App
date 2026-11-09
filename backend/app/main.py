from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import public_router, router
from .api.routes.google_calendar import GoogleCalendar
from .core.auth import Authenticator, ClerkAuthenticator
from .core.config import Settings
from .core.redaction import install_log_redaction
from .db import make_engine, make_session_factory
from .services.goodreads import ImportStore
from .services.google_calendar import GoogleCalendarClient


def create_app(
    settings: Settings | None = None, authenticator: Authenticator | None = None,
    google_transport: httpx.BaseTransport | None = None,
) -> FastAPI:
    settings = settings or Settings()
    if authenticator is None and settings.clerk_configured:
        authenticator = ClerkAuthenticator(settings)
    if authenticator is None and settings.app_env not in {"development", "test"}:
        raise RuntimeError("Production startup refused: Clerk authentication is not configured")
    engine = make_engine(
        settings.database_url,
        settings.postgres_password.get_secret_value() if settings.postgres_password else None,
    )

    install_log_redaction()
    # Optional integration: without Google credentials Studium works exactly as before.
    google = (
        GoogleCalendar(settings, GoogleCalendarClient(settings, google_transport))
        if settings.google_configured else None
    )

    @asynccontextmanager
    async def lifespan(app):
        yield
        if google is not None:
            google.client.close()
        engine.dispose()

    app = FastAPI(title="Executive Function API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    # Without an authenticator every protected endpoint answers 503; nothing defaults to a user.
    app.state.authenticator = authenticator
    app.state.google = google
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.import_store = ImportStore()
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"], allow_credentials=False,
    )
    app.include_router(public_router)
    app.include_router(router)
    return app


app = create_app()
