"""Synthetic current-ledger replay against a disposable PostgreSQL restore."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from health_api.application.restore_erasure import ErasureLedgerSnapshot, replay_restore_erasure
from health_api.integrations.object_storage import LocalObjectStorage, ObjectCleanupPending
from health_api.persistence.models import OwnerErasureLedger, Source, User


def test_replay_erases_only_current_marked_owner_and_blocks_new_writes(
    db_session: Session, tmp_path: Path
) -> None:
    owner, other = uuid4(), uuid4()
    db_session.add_all(
        [User(id=owner, display_timezone="UTC"), User(id=other, display_timezone="UTC")]
    )
    db_session.flush()
    db_session.add_all(
        [
            Source(
                id=uuid4(),
                owner_id=owner,
                source_key="synthetic-restore",
                source_kind="manual",
                display_name="Synthetic deleted source",
            ),
            Source(
                id=uuid4(),
                owner_id=other,
                source_key="synthetic-restore",
                source_kind="manual",
                display_name="Synthetic retained source",
            ),
        ]
    )
    db_session.commit()
    storage = LocalObjectStorage(tmp_path / "isolated-private", max_size_bytes=1024)
    snapshot = ErasureLedgerSnapshot(observed_at=datetime.now(UTC), owners=(owner,))
    result = replay_restore_erasure(
        db_session,
        snapshot,
        backup_created_at=datetime.now(UTC) - timedelta(days=1),
        object_storage=storage,
    )
    assert result == {"completed": 1, "pending": 0}
    assert db_session.get(User, owner).lifecycle == "erased"
    assert db_session.get(OwnerErasureLedger, owner) is not None
    assert list(db_session.scalars(select(Source.owner_id))) == [other]


def test_pending_object_cleanup_blocks_completion(db_session: Session) -> None:
    class PendingStorage:
        def delete_owner(self, _owner):
            raise ObjectCleanupPending

    owner = uuid4()
    db_session.add(User(id=owner, display_timezone="UTC"))
    db_session.commit()
    snapshot = ErasureLedgerSnapshot(observed_at=datetime.now(UTC), owners=(owner,))
    assert replay_restore_erasure(
        db_session,
        snapshot,
        backup_created_at=datetime.now(UTC) - timedelta(days=1),
        object_storage=PendingStorage(),
    ) == {"completed": 0, "pending": 1}
    assert db_session.get(User, owner).lifecycle == "deleting"


def test_stale_ledger_is_rejected_before_database_work(db_session: Session, tmp_path: Path) -> None:
    snapshot = ErasureLedgerSnapshot(observed_at=datetime.now(UTC) - timedelta(days=2), owners=())
    with pytest.raises(ValueError, match="independently retained"):
        replay_restore_erasure(
            db_session,
            snapshot,
            backup_created_at=datetime.now(UTC) - timedelta(days=1),
            object_storage=LocalObjectStorage(tmp_path / "synthetic", max_size_bytes=1024),
        )
