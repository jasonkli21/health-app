"""SQLAlchemy engine and session factories. Schema creation belongs to Alembic."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def create_database_engine(
    database_url: str,
    *,
    pool_size: int = 5,
    max_overflow: int = 0,
    pool_timeout_seconds: float = 3.0,
    connect_timeout_seconds: int = 5,
) -> Engine:
    return create_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout_seconds,
        pool_recycle=1800,
        connect_args={"connect_timeout": connect_timeout_seconds},
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
