from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .core.config import Settings
from .db import make_engine, make_session_factory


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    if settings.app_env not in {"development", "test"}:
        raise RuntimeError("Production startup refused: authentication is not implemented")
    engine = make_engine(
        settings.database_url,
        settings.postgres_password.get_secret_value() if settings.postgres_password else None,
    )

    @asynccontextmanager
    async def lifespan(app):
        yield
        engine.dispose()

    app = FastAPI(title="Executive Function API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"], allow_credentials=False,
    )
    app.include_router(router)
    return app


app = create_app()
