"""Prepare a local Health reservation without sending or accepting PAS responses."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from health_api.application.r5_health_source import (
    R5PreviewUnavailable,
    R5SourceAuthority,
    read_r5_health_preference,
    require_current_r5_source_authority,
    resolve_r5_owner,
)
from health_api.config.settings import Settings
from health_api.persistence.models import R5PreviewReservation

R5_PREVIEW_TITLE = "Health preference preview"


@dataclass(frozen=True)
class R5CallerTarget:
    """Offline internal binding fields. The recipient digest covers runtime, model and recipient."""

    pas_owner_id: UUID
    client_id: UUID
    branch_id: UUID
    recipient_digest: str


@dataclass(frozen=True)
class R5OriginalKeys:
    create: UUID
    preview: UUID


def reserve_r5_operation_keys(
    sessions: sessionmaker[Session],
    settings: Settings,
    *,
    intent_id: UUID,
    request: bytes,
    authority: R5SourceAuthority,
    target: R5CallerTarget,
    create_request_digest: str,
    reauthorize: Callable[[], tuple[R5SourceAuthority, R5CallerTarget] | None],
) -> R5OriginalKeys:
    """Commit two original keys and the local create intent before any future transport.

    The supplied digests are offline inputs. Exact PAS request digests, preview body, verified
    create outcome and GET-only preview observation require the frozen C3 contract.
    """
    if not all(
        re.fullmatch(r"[0-9a-f]{64}", digest)
        for digest in (target.recipient_digest, create_request_digest)
    ):
        raise R5PreviewUnavailable

    def reauthorize_source() -> R5SourceAuthority | None:
        current = reauthorize()
        if current is None or current[1] != target:
            return None
        return current[0]

    owner_id, source = read_r5_health_preference(
        sessions, settings, request, authority, reauthorize_source
    )
    # Local reservation encoding only. Never use this as a PAS canonicalization or receipt.
    binding_digest = hashlib.sha256(
        json.dumps(
            {
                "owner": str(owner_id),
                "firebase_issuer": authority.identity.issuer,
                "firebase_uid": authority.identity.subject,
                "enrollment": str(authority.enrollment_id),
                "generation": authority.enrollment_generation,
                "installation": str(authority.installation_id),
                "object": str(authority.selection.object_id),
                "revision": authority.selection.revision,
                "permission_version": source.items[0].permission_dependencies[0].version,
                "pas_owner": str(target.pas_owner_id),
                "client": str(target.client_id),
                "branch": str(target.branch_id),
                "recipient": target.recipient_digest,
                "title": R5_PREVIEW_TITLE,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    require_current_r5_source_authority(settings, authority, reauthorize_source())
    with sessions() as session, session.begin():
        session.execute(text("SET LOCAL statement_timeout = '1800ms'"))
        if resolve_r5_owner(session, authority) != owner_id:
            raise R5PreviewUnavailable
        inserted = session.scalars(
            insert(R5PreviewReservation)
            .values(
                [
                    {
                        "original_key": uuid4(),
                        "owner_id": owner_id,
                        "intent_id": intent_id,
                        "operation": operation,
                        "object_id": authority.selection.object_id,
                        "object_revision": authority.selection.revision,
                        "binding_digest": binding_digest,
                        "request_digest": create_request_digest if operation == "create" else None,
                    }
                    for operation in ("create", "preview")
                ]
            )
            .on_conflict_do_nothing(constraint="uq_r5_preview_reservations_intent_operation")
            .returning(R5PreviewReservation.original_key)
        ).all()
        if len(inserted) == 1:
            raise R5PreviewUnavailable
        reservations = {
            row.operation: row
            for row in session.scalars(
                select(R5PreviewReservation).where(
                    R5PreviewReservation.intent_id == intent_id,
                    R5PreviewReservation.owner_id == owner_id,
                )
            )
        }
        if (
            reservations.keys() != {"create", "preview"}
            or any(
                row.binding_digest != binding_digest
                or row.object_id != authority.selection.object_id
                or row.object_revision != authority.selection.revision
                for row in reservations.values()
            )
            or reservations["create"].request_digest != create_request_digest
        ):
            raise R5PreviewUnavailable
        return R5OriginalKeys(
            reservations["create"].original_key, reservations["preview"].original_key
        )
