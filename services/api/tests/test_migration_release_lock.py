from __future__ import annotations

from unittest.mock import Mock

import pytest
from health_api.persistence.migration_lock import LOCK_KEY, migration_release_lock
from sqlalchemy import Engine, text


def connection(*answers: bool) -> Mock:
    result = Mock()
    result.in_transaction.return_value = False
    result.execute.return_value.scalar_one.side_effect = answers
    return result


def test_lock_queries_do_not_steal_alembic_transaction() -> None:
    conn = connection(True)
    with migration_release_lock(conn):
        assert conn.rollback.call_count == 1
    assert "pg_advisory_unlock" in str(conn.execute.call_args.args[0])
    assert conn.rollback.call_count == 2


def test_contention_is_bounded_and_sanitized() -> None:
    conn = connection(False)
    with (
        pytest.raises(RuntimeError, match="could not be acquired"),
        migration_release_lock(conn, wait_seconds=0),
    ):
        pytest.fail("must not migrate")
    assert conn.execute.call_count == 1


def test_aborted_migration_rolls_back_before_unlock_and_preserves_error() -> None:
    conn = connection(True)
    with pytest.raises(ValueError, match="migration failed"), migration_release_lock(conn):
        raise ValueError("migration failed")
    assert conn.rollback.call_count == 3
    assert "pg_advisory_unlock" in str(conn.execute.call_args.args[0])


def test_broken_cleanup_invalidates_connection() -> None:
    conn = connection(True)
    conn.execute.side_effect = [conn.execute.return_value, RuntimeError("secret SQL")]
    with pytest.raises(RuntimeError, match="cleanup failed"), migration_release_lock(conn):
        pass
    conn.invalidate.assert_called_once()


def test_parallel_postgres_executions_and_error_cleanup(postgres_engine: Engine) -> None:
    with postgres_engine.connect() as first, postgres_engine.connect() as second:
        with (
            migration_release_lock(first),
            pytest.raises(RuntimeError, match="could not be acquired"),
            migration_release_lock(second, wait_seconds=0),
        ):
            pytest.fail("concurrent migration")
        with pytest.raises(Exception, match="division by zero"), migration_release_lock(first):
            first.execute(text("SELECT 1 / 0"))
    with postgres_engine.connect() as third:
        assert third.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": LOCK_KEY}
        ).scalar_one()
        third.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_KEY})
