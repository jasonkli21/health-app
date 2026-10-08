"""SQLAlchemy engine and session factories. Schema creation belongs to Alembic."""

from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

_PRE_PING_STATEMENT_TIMEOUT = "1000ms"


def _set_local_statement_timeout(dbapi_connection: Any, value: str) -> None:
    with dbapi_connection.cursor() as cursor:
        cursor.execute(f"SET LOCAL statement_timeout = '{value}'")


def create_database_engine(
    database_url: str,
    *,
    pool_size: int = 5,
    max_overflow: int = 0,
    pool_timeout_seconds: float = 1.0,
    connect_timeout_seconds: int = 1,
) -> Engine:
    engine = create_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout_seconds,
        pool_recycle=1800,
        connect_args={
            "connect_timeout": connect_timeout_seconds,
            "options": f"-c statement_timeout={_PRE_PING_STATEMENT_TIMEOUT}",
        },
    )

    @event.listens_for(engine, "checkout")
    def clear_pre_ping_timeout(
        dbapi_connection: Any, _connection_record: Any, _connection_proxy: Any
    ) -> None:
        # The startup setting bounds SQLAlchemy's pre-ping. Reset it after ping
        # within this transaction so domain queries keep their existing
        # per-operation policies. Pool rollback restores the idle default.
        _set_local_statement_timeout(dbapi_connection, "0")

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
