"""Serialize independent Alembic executions with a session advisory lock."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from time import monotonic, sleep

from sqlalchemy import Connection, text

LOCK_KEY = 0x4845414C54484D47
WAIT_SECONDS = 30.0


@contextmanager
def migration_release_lock(
    connection: Connection, wait_seconds: float = WAIT_SECONDS
) -> Iterator[None]:
    deadline = monotonic() + wait_seconds
    caller_transaction = connection.in_transaction()
    acquired = False
    try:
        while not acquired:
            acquired = bool(
                connection.execute(
                    text("SELECT pg_try_advisory_lock(:key)"), {"key": LOCK_KEY}
                ).scalar_one()
            )
            # The session lock survives rollback. End only our implicit transaction,
            # so Alembic owns and commits its real migration transaction.
            if not caller_transaction:
                connection.rollback()
            if acquired:
                break
            if monotonic() >= deadline:
                raise RuntimeError("Migration release lock is busy.")
            sleep(min(0.1, max(0.0, deadline - monotonic())))
    except Exception:  # noqa: BLE001 - sanitize database/driver details at release boundary
        if not caller_transaction:
            connection.rollback()
        raise RuntimeError("Migration release lock could not be acquired.") from None

    failed = False
    try:
        yield
    except BaseException:
        failed = True
        # An aborted PostgreSQL transaction cannot execute the unlock statement.
        connection.rollback()
        raise
    finally:
        try:
            connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_KEY})
            if not caller_transaction or failed:
                connection.rollback()
        except Exception:  # noqa: BLE001 - sanitize database/driver details at release boundary
            # Closing/invalidation releases session locks even on a broken socket.
            connection.invalidate()
            if not failed:
                raise RuntimeError("Migration release lock cleanup failed.") from None
