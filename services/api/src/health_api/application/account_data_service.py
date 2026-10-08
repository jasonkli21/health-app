"""Owner-scoped data export and restartable domain erasure operations."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from io import StringIO
from typing import Any
from uuid import UUID

from health_api.integrations.object_storage import (
    ObjectCleanupPending,
    ObjectStorage,
    ObjectStorageUnavailable,
)
from health_api.persistence.models import Base, OwnerDeletionJob, OwnerErasureLedger, User
from sqlalchemy import Select, literal_column, select, text
from sqlalchemy.orm import Session

_INTERNAL_OWNER_TABLES = {"owner_deletion_jobs", "owner_erasure_ledger"}
_OWNER_DATA_TABLE_NAMES = frozenset(
    {
        "action_proposals",
        "daily_snapshot_markers",
        "healthkit_import_batches",
        "sources",
        "action_proposal_revisions",
        "health_objects",
        "healthkit_source_preferences",
        "action_command_receipts",
        "action_proposal_events",
        "analytics_artifacts",
        "events",
        "health_object_revisions",
        "health_relationships",
        "healthkit_import_identities",
        "observations",
        "planning_resources",
        "profile_items",
        "tracker_schema_versions",
        "analytics_evidence",
        "event_observation_links",
        "planning_links",
        "planning_schedule_identities",
        "planning_occurrence_overrides",
        "planning_schedules",
        "planning_occurrence_actions",
    }
)
_EXPORT_ROW_LIMIT = 100_000
_EXPORT_BYTE_LIMIT = 20 * 1024 * 1024
_ERASURE_BATCH_SIZE = 1000
_ERASURE_ROWS_PER_REQUEST = 10_000


class AccountDataNotFound(Exception):
    """The authenticated owner's account data or deletion request was not found."""


class AccountDataConflict(Exception):
    """The owner's account lifecycle does not allow the requested operation."""


class AccountExportLimitExceeded(Exception):
    """The owner snapshot exceeds the bounded synchronous export limit."""


def _owner_tables() -> list[Any]:
    actual = {
        table.name
        for table in Base.metadata.sorted_tables
        if "owner_id" in table.c and table.name not in _INTERNAL_OWNER_TABLES
    }
    if actual != _OWNER_DATA_TABLE_NAMES:
        raise RuntimeError("owner export and erasure inventory requires reconciliation")
    return [table for table in Base.metadata.sorted_tables if table.name in _OWNER_DATA_TABLE_NAMES]


def _json_value(value: Any) -> Any:
    if isinstance(value, (UUID, datetime, date)):
        return value.isoformat() if isinstance(value, (datetime, date)) else str(value)
    if isinstance(value, dict):
        return {str(key): _json_value(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(child) for child in value]
    return value


def export_owner_snapshot(session: Session, owner_id: UUID) -> str:
    """Serialize every current owner table in one repeatable-read database snapshot."""
    with session.begin():
        session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
        session.execute(text("SET LOCAL statement_timeout = '2s'"))
        user = session.get(User, owner_id)
        if user is None or user.lifecycle != "active":
            raise AccountDataNotFound

        buffer = StringIO()
        serialized_bytes = 0
        encoder = json.JSONEncoder(ensure_ascii=False, separators=(",", ":"), allow_nan=False)

        def write(value: str) -> None:
            nonlocal serialized_bytes
            serialized_bytes += len(value.encode("utf-8"))
            if serialized_bytes > _EXPORT_BYTE_LIMIT:
                raise AccountExportLimitExceeded
            buffer.write(value)

        def write_json(value: Any) -> None:
            for piece in encoder.iterencode(value):
                write(piece)

        created_at = session.execute(text("SELECT transaction_timestamp()")).scalar_one()
        owner_payload = {
            "id": str(user.id),
            "display_timezone": user.display_timezone,
            "daily_sequence": user.daily_sequence,
            "created_at": _json_value(user.created_at),
        }

        write("{")
        write_json("format")
        write(":")
        write_json("personal-health-owner-export-v1")
        write(",")
        write_json("schema_version")
        write(":1,")
        write_json("created_at")
        write(":")
        write_json(_json_value(created_at))
        write(",")
        write_json("snapshot_as_of")
        write(":")
        write_json(_json_value(created_at))
        write(",")
        write_json("owner")
        write(":")
        write_json(owner_payload)
        write(",")
        write_json("data")
        write(":{")

        table_counts: dict[str, int] = {}
        total_rows = 0
        for table_index, table in enumerate(_owner_tables()):
            if table_index:
                write(",")
            write_json(table.name)
            write(": [")
            query: Select[Any] = select(*table.c).where(table.c.owner_id == owner_id)
            primary_key = list(table.primary_key.columns)
            if primary_key:
                query = query.order_by(*primary_key)
            remaining = _EXPORT_ROW_LIMIT - total_rows
            rows = session.execute(
                query.limit(remaining + 1).execution_options(yield_per=100)
            ).mappings()
            table_count = 0
            for row in rows:
                if total_rows >= _EXPORT_ROW_LIMIT:
                    raise AccountExportLimitExceeded
                if table_count:
                    write(",")
                write_json({column: _json_value(value) for column, value in row.items()})
                table_count += 1
                total_rows += 1
            table_counts[table.name] = table_count
            write("]")

        write("},")
        write_json("manifest")
        write(":")
        write_json(
            {
                "table_row_counts": table_counts,
                "total_rows": total_rows,
                "record_files_included": False,
                "record_files_status": "record_ingress_not_enabled",
            }
        )
        write("}")
        return buffer.getvalue()


def begin_owner_deletion(session: Session, owner_id: UUID, request_id: UUID) -> OwnerDeletionJob:
    """Commit the owner write freeze and durable erasure intent before cleanup starts."""
    with session.begin():
        # Serialize a request ID independently of the owner row. The latter
        # prevents two distinct requests from freezing the same owner at once;
        # this advisory lock also makes overlapping identical retries replay.
        request_lock = int.from_bytes(request_id.bytes[:8], "big", signed=True)
        session.execute(
            text("SELECT pg_advisory_xact_lock(:request_lock)"), {"request_lock": request_lock}
        )
        job = session.get(OwnerDeletionJob, request_id)
        if job is not None:
            if job.owner_id != owner_id:
                raise AccountDataNotFound
            if job.status != "completed":
                job.status = "running"
                job.error_code = None
                job.updated_at = datetime.now(UTC)
            return job

        user = session.execute(
            select(User).where(User.id == owner_id).with_for_update()
        ).scalar_one_or_none()
        if user is None:
            raise AccountDataNotFound
        # Check again after owner serialization for deployments where request
        # IDs are allocated before the lock is acquired.
        job = session.get(OwnerDeletionJob, request_id)
        if job is not None:
            if job.owner_id != owner_id:
                raise AccountDataNotFound
            if job.status != "completed":
                job.status = "running"
                job.error_code = None
                job.updated_at = datetime.now(UTC)
            return job
        if user.lifecycle != "active":
            raise AccountDataConflict

        user.lifecycle = "deleting"
        job = OwnerDeletionJob(id=request_id, owner_id=owner_id, status="running")
        session.add(job)
        session.flush()
        return job


def load_owner_deletion(session: Session, owner_id: UUID, request_id: UUID) -> OwnerDeletionJob:
    job = session.get(OwnerDeletionJob, request_id)
    if job is None or job.owner_id != owner_id:
        raise AccountDataNotFound
    return job


def find_owner_deletion(session: Session, owner_id: UUID) -> OwnerDeletionJob:
    """Discover the authenticated owner's durable deletion job for recovery."""
    job = session.scalar(
        select(OwnerDeletionJob)
        .where(OwnerDeletionJob.owner_id == owner_id)
        .order_by(OwnerDeletionJob.requested_at.desc(), OwnerDeletionJob.id.desc())
        .limit(1)
    )
    if job is None:
        raise AccountDataNotFound
    return job


def process_owner_deletion(
    session: Session,
    owner_id: UUID,
    request_id: UUID,
    object_storage: ObjectStorage,
) -> OwnerDeletionJob:
    """Retry private-object cleanup, then erase every owner table in dependency order."""
    with session.begin():
        job = load_owner_deletion(session, owner_id, request_id)
        if job.status == "completed":
            return job

    try:
        try:
            object_storage.delete_owner(owner_id)
        except ObjectCleanupPending:
            return load_owner_deletion(session, owner_id, request_id)
        except ObjectStorageUnavailable:
            return _record_deletion_failure(
                session, owner_id, request_id, "object_storage_unavailable"
            )

        remaining_budget = _ERASURE_ROWS_PER_REQUEST
        for table in reversed(_owner_tables()):
            while remaining_budget > 0:
                batch_size = min(_ERASURE_BATCH_SIZE, remaining_budget)
                with session.begin():
                    session.execute(text("SET LOCAL statement_timeout = '2s'"))
                    job = session.execute(
                        select(OwnerDeletionJob)
                        .where(
                            OwnerDeletionJob.id == request_id,
                            OwnerDeletionJob.owner_id == owner_id,
                        )
                        .with_for_update()
                    ).scalar_one_or_none()
                    user = session.execute(
                        select(User).where(User.id == owner_id).with_for_update()
                    ).scalar_one_or_none()
                    if job is None or user is None:
                        raise AccountDataNotFound
                    if job.status == "completed":
                        return job
                    if user.lifecycle not in {"deleting", "erased"}:
                        raise AccountDataConflict

                    primary_key = list(table.primary_key.columns)
                    batch_query = (
                        select(literal_column("ctid"))
                        .select_from(table)
                        .where(table.c.owner_id == owner_id)
                    )
                    if primary_key:
                        batch_query = batch_query.order_by(*primary_key)
                    batch_ctids = batch_query.limit(batch_size)
                    result = session.execute(
                        table.delete().where(literal_column("ctid").in_(batch_ctids))
                    )
                    deleted = result.rowcount or 0
                remaining_budget -= deleted
                if deleted < batch_size:
                    break
        if remaining_budget <= 0:
            return load_owner_deletion(session, owner_id, request_id)

        with session.begin():
            session.execute(text("SET LOCAL statement_timeout = '2s'"))
            job = session.execute(
                select(OwnerDeletionJob)
                .where(OwnerDeletionJob.id == request_id, OwnerDeletionJob.owner_id == owner_id)
                .with_for_update()
            ).scalar_one_or_none()
            user = session.execute(
                select(User).where(User.id == owner_id).with_for_update()
            ).scalar_one_or_none()
            if job is None or user is None:
                raise AccountDataNotFound
            if job.status == "completed":
                return job
            if user.lifecycle not in {"deleting", "erased"}:
                raise AccountDataConflict
            if session.get(OwnerErasureLedger, owner_id) is None:
                session.add(OwnerErasureLedger(owner_id=owner_id))
            user.lifecycle = "erased"
            user.display_timezone = "UTC"
            user.daily_sequence = 0
            job.status = "completed"
            job.error_code = None
            job.completed_at = datetime.now(UTC)
            job.updated_at = job.completed_at
            session.flush()
            return job
    except (AccountDataNotFound, AccountDataConflict):
        raise
    except Exception:  # noqa: BLE001 - keep cleanup details out of health-domain responses
        return _record_deletion_failure(session, owner_id, request_id, "database_cleanup_failed")


def _record_deletion_failure(
    session: Session, owner_id: UUID, request_id: UUID, error_code: str
) -> OwnerDeletionJob:
    with session.begin():
        job = session.execute(
            select(OwnerDeletionJob)
            .where(OwnerDeletionJob.id == request_id, OwnerDeletionJob.owner_id == owner_id)
            .with_for_update()
        ).scalar_one_or_none()
        if job is None:
            raise AccountDataNotFound
        if job.status != "completed":
            job.status = "failed"
            job.error_code = error_code
            job.updated_at = datetime.now(UTC)
        return job
