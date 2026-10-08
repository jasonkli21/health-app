"""FastAPI application construction; schema changes remain Alembic-owned."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from health_api.api.account_data import router as account_data_router
from health_api.api.ai import router as ai_router
from health_api.api.analytics import router as analytics_router
from health_api.api.daily import router as daily_router
from health_api.api.errors import install_error_handlers
from health_api.api.healthkit_imports import router as healthkit_import_router
from health_api.api.middleware import RequestBoundaryMiddleware
from health_api.api.planning import router as planning_router
from health_api.api.profile import router as profile_router
from health_api.api.proposals import router as proposals_router
from health_api.config.settings import Settings, get_settings
from health_api.integrations.firebase_auth import FirebaseTokenVerifier, IdentityVerifier
from health_api.integrations.object_storage import create_object_storage
from health_api.integrations.personal_ai import create_personal_ai_adapter
from health_api.persistence.database import create_database_engine, create_session_factory


def create_app(
    settings: Settings | None = None,
    engine: Engine | None = None,
    identity_verifier: IdentityVerifier | None = None,
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
            "Owner-scoped account data, Profile, daily Event/Observation, planning, and local AI "
            "context preview/search. Live Personal AI messaging is unavailable until the "
            "Application Integration Contract is implemented and reviewed. "
            "Identity is resolved from server configuration or verified Firebase bearer tokens. "
            "Request bodies are limited to 65,536 bytes except normalized HealthKit batches, "
            "which are limited to 1,048,576 bytes."
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
    app.state.personal_ai_status = create_personal_ai_adapter()
    if identity_verifier is not None:
        app.state.identity_verifier = identity_verifier
    elif configured_settings.auth_mode == "firebase":
        app.state.identity_verifier = FirebaseTokenVerifier(
            configured_settings.firebase_project_id or "",
            timeout_seconds=configured_settings.auth_http_timeout_seconds,
            max_in_flight=configured_settings.auth_max_in_flight,
        )
    app.add_middleware(
        RequestBoundaryMiddleware,
        max_body_bytes=65_536,
        path_limits={"/imports/healthkit/batches": 1_048_576},
    )
    install_error_handlers(app)
    app.include_router(profile_router)
    app.include_router(daily_router)
    app.include_router(planning_router)
    app.include_router(ai_router)
    app.include_router(proposals_router)
    app.include_router(analytics_router)
    app.include_router(healthkit_import_router)
    app.include_router(account_data_router)

    @app.get("/healthz", tags=["system"], operation_id="healthcheck")
    def healthcheck() -> dict[str, str]:
        """Return process liveness without exposing health-domain data or DB state."""
        return {"status": "ok"}

    @app.get(
        "/readyz",
        tags=["system"],
        operation_id="readinesscheck",
        response_model=dict[str, str],
        responses={
            503: {
                "model": dict[str, str],
                "description": "The canonical Health database is unavailable.",
            }
        },
    )
    def readinesscheck() -> JSONResponse:
        """Check canonical database availability without returning connection details."""
        try:
            with database_engine.connect() as connection:
                connection.execute(text("SELECT 1")).scalar_one()
        except SQLAlchemyError:
            return JSONResponse(status_code=503, content={"status": "unavailable"})
        return JSONResponse(status_code=200, content={"status": "ok"})

    return app


app = create_app()
