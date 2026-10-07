"""FastAPI application construction; schema changes remain Alembic-owned."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from health_api.api.ai import router as ai_router
from health_api.api.analytics import router as analytics_router
from health_api.api.daily import router as daily_router
from health_api.api.errors import install_error_handlers
from health_api.api.middleware import RequestBoundaryMiddleware
from health_api.api.planning import router as planning_router
from health_api.api.profile import router as profile_router
from health_api.api.proposals import router as proposals_router
from health_api.config.settings import Settings, get_settings
from health_api.integrations.firebase_auth import FirebaseTokenVerifier, IdentityVerifier
from health_api.integrations.object_storage import create_object_storage
from health_api.integrations.personal_ai import PersonalAIAdapter, create_personal_ai_adapter
from health_api.persistence.database import create_database_engine, create_session_factory


def create_app(
    settings: Settings | None = None,
    engine: Engine | None = None,
    identity_verifier: IdentityVerifier | None = None,
    personal_ai_adapter: PersonalAIAdapter | None = None,
) -> FastAPI:
    configured_settings = settings or get_settings()
    database_engine = engine or create_database_engine(
        configured_settings.database_url.get_secret_value(),
        pool_size=configured_settings.database_pool_size,
        max_overflow=configured_settings.database_max_overflow,
        pool_timeout_seconds=configured_settings.database_pool_timeout_seconds,
        connect_timeout_seconds=configured_settings.database_connect_timeout_seconds,
    )
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
            "Owner-scoped Profile, daily Event/Observation, planning, and read-only Assistant APIs. "
            "Identity is resolved from server configuration or verified Firebase bearer tokens. "
            "Request bodies are limited to 65,536 bytes."
        ),
        docs_url=None if configured_settings.app_env == "cloud" else "/docs",
        redoc_url=None if configured_settings.app_env == "cloud" else "/redoc",
        openapi_url=None if configured_settings.app_env == "cloud" else "/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = configured_settings
    app.state.engine = database_engine
    app.state.session_factory = sessions
    app.state.object_storage = create_object_storage(configured_settings)
    app.state.personal_ai_adapter = personal_ai_adapter or create_personal_ai_adapter()
    if identity_verifier is not None:
        app.state.identity_verifier = identity_verifier
    elif configured_settings.auth_mode == "firebase":
        app.state.identity_verifier = FirebaseTokenVerifier(
            configured_settings.firebase_project_id or "",
            timeout_seconds=configured_settings.auth_http_timeout_seconds,
            max_in_flight=configured_settings.auth_max_in_flight,
        )
    app.add_middleware(RequestBoundaryMiddleware, max_body_bytes=65_536)
    install_error_handlers(app)
    app.include_router(profile_router)
    app.include_router(daily_router)
    app.include_router(planning_router)
    app.include_router(ai_router)
    app.include_router(proposals_router)
    app.include_router(analytics_router)

    @app.get("/healthz", tags=["system"], operation_id="healthcheck")
    def healthcheck() -> dict[str, str]:
        """Return process liveness without exposing health-domain data or DB state."""
        return {"status": "ok"}

    return app


app = create_app()
