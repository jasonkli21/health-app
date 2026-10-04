from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="session")
def postgres_engine() -> Generator[Engine, None, None]:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("PostgreSQL integration tests require TEST_DATABASE_URL")
    database_name = make_url(database_url).database or ""
    if "test" not in database_name and "phase1" not in database_name:
        pytest.fail(
            "TEST_DATABASE_URL must name a disposable database containing 'test' or 'phase1'"
        )

    engine = create_engine(database_url, echo=False, pool_pre_ping=True)
    config = Config(str(ROOT / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(postgres_engine: Engine) -> Generator[Session, None, None]:
    with postgres_engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE TABLE health_relationships, health_object_revisions, "
                "profile_items, health_objects, sources, users CASCADE"
            )
        )
    factory = sessionmaker(bind=postgres_engine, expire_on_commit=False)
    with factory() as session:
        yield session
