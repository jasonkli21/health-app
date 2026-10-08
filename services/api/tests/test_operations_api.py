from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from health_api.config.settings import Settings
from health_api.main import create_app
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError


def _settings(
    database_url: str = "postgresql+psycopg://health:health@127.0.0.1:1/health_test",
) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=database_url,
        database_pool_timeout_seconds=0.5,
        database_connect_timeout_seconds=1,
    )


def test_healthz_is_process_liveness_without_database_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app(_settings())

    def unexpected_database_access() -> None:
        raise AssertionError("/healthz must not access the database")

    monkeypatch.setattr(app.state.engine, "connect", unexpected_database_access)
    with TestClient(app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_checks_database_connection(postgres_engine: Engine) -> None:
    with TestClient(create_app(_settings(), engine=postgres_engine)) as client:
        response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_returns_sanitized_503_when_database_is_unavailable() -> None:
    config = _settings("postgresql+psycopg://health:secret@127.0.0.1:1/health_test")
    with TestClient(create_app(config)) as client:
        liveness = client.get("/healthz")
        readiness = client.get("/readyz")

    assert liveness.status_code == 200
    assert readiness.status_code == 503
    assert readiness.json() == {"status": "unavailable"}
    assert "secret" not in readiness.text
    assert "127.0.0.1" not in readiness.text


def test_readyz_returns_sanitized_503_when_query_fails() -> None:
    app = create_app(_settings())
    with patch.object(app.state.engine, "connect") as connect:
        connect.return_value.__enter__.return_value.execute.side_effect = SQLAlchemyError(
            "SECRET_QUERY_DETAIL"
        )
        with TestClient(app) as client:
            response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert "SECRET_QUERY_DETAIL" not in response.text
