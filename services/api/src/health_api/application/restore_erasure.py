"""Replay current owner erasure intent into an isolated Health restore.

This application primitive does not promote a restored database or invoke cloud
backup APIs. Operators must supply current markers independently of the backup,
stop writers, and require pending=0 before promotion.
"""

from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from health_api.application.account_data_service import _owner_tables, process_owner_deletion
from health_api.integrations.object_storage import ObjectStorage
from health_api.persistence.models import OwnerDeletionJob, OwnerErasureLedger, User


class ErasureLedgerSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["health-erasure-ledger-v1"] = "health-erasure-ledger-v1"
    observed_at: AwareDatetime
    owners: tuple[UUID, ...] = Field(max_length=10000)

    @field_validator("owners")
    @classmethod
    def unique_owners(cls, owners: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(set(owners)) != len(owners):
            raise ValueError("duplicate erasure owner")
        return owners


def ledger_snapshot(session: Session) -> ErasureLedgerSnapshot:
    # Include a requested deletion even if private cleanup has not completed.
    query = select(OwnerErasureLedger.owner_id).union(select(OwnerDeletionJob.owner_id))
    return ErasureLedgerSnapshot(
        observed_at=datetime.now(UTC), owners=tuple(session.scalars(query).all())
    )


def replay_restore_erasure(
    session: Session,
    snapshot: ErasureLedgerSnapshot,
    *,
    backup_created_at: datetime,
    object_storage: ObjectStorage,
) -> dict[str, int]:
    if (
        backup_created_at.tzinfo is None
        or not backup_created_at
        <= snapshot.observed_at
        <= datetime.now(UTC) + timedelta(seconds=60)
    ):
        raise ValueError("current independently retained erasure ledger required")
    if session.in_transaction():
        raise ValueError("restore replay requires its own transactions")
    completed = pending = 0
    for owner_id in snapshot.owners:
        request_id = uuid5(NAMESPACE_URL, f"health-restore-erasure-v1:{owner_id}")
        with session.begin():
            user = session.scalar(select(User).where(User.id == owner_id).with_for_update())
            if user is None:
                user = User(id=owner_id, display_timezone="UTC", lifecycle="deleting")
                session.add(user)
                session.flush()
            else:
                user.lifecycle = "deleting"
            # Retain the fence before cleanup. A historical completed job is
            # reset only in this explicitly isolated restore application path.
            if session.get(OwnerErasureLedger, owner_id) is None:
                session.add(OwnerErasureLedger(owner_id=owner_id))
            job = session.get(OwnerDeletionJob, request_id)
            if job is None:
                session.add(OwnerDeletionJob(id=request_id, owner_id=owner_id, status="running"))
            else:
                if job.owner_id != owner_id:
                    raise ValueError("restore job owner mismatch")
                job.status, job.completed_at, job.error_code = "running", None, None
        job = process_owner_deletion(session, owner_id, request_id, object_storage)
        is_completed = job.status == "completed"
        remaining = sum(
            session.scalar(
                select(func.count()).select_from(table).where(table.c.owner_id == owner_id)
            )
            or 0
            for table in _owner_tables()
        )
        session.rollback()  # End observation before the next owner's transaction.
        if is_completed and not remaining:
            completed += 1
        else:
            pending += 1
    return {"completed": completed, "pending": pending}
