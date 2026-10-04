"""FastAPI application construction; schema changes remain Alembic-owned."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from health_api.api.daily import router as daily_router
from health_api.api.errors import install_error_handlers
from health_api.api.middleware import RequestBoundaryMiddleware
from health_api.api.profile import router as profile_router
from health_api.config.settings import Settings, get_settings
from health_api.persistence.database import create_database_engine, create_session_factory


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    configured_settings = settings or get_settings()
    database_engine = engine or create_database_engine(configured_settings.database_url)
    owns_engine = engine is None
    sessions: sessionmaker[Session] = create_session_factory(database_engine)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        if owns_engine:
            database_engine.dispose()

    app = FastAPI(
        title="Personal Health API",
        version="1.0.0",
        description=(
            "Owner-scoped Profile v1 and daily Event/Observation v1 APIs for private local development. "
            "The server principal is configured outside request data. "
            "Request bodies are limited to 65,536 bytes."
        ),
        lifespan=lifespan,
    )
    app.state.settings = configured_settings
    app.state.engine = database_engine
    app.state.session_factory = sessions
    app.add_middleware(RequestBoundaryMiddleware, max_body_bytes=65_536)
    install_error_handlers(app)
    app.include_router(profile_router)
    app.include_router(daily_router)

    @app.get("/healthz", tags=["system"], operation_id="healthcheck")
    def healthcheck() -> dict[str, str]:
        """Return process liveness without exposing health-domain data or DB state."""
        return {"status": "ok"}

    return app


app = create_app()
