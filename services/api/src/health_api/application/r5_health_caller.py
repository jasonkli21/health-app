"""Prepare a local Health reservation without sending or accepting PAS responses."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
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
from health_api.integrations.personal_ai_preview_receipt import (
    MAX_RESPONSE_BYTES,
    PROFILE_PATH,
    canonical_digest,
    canonical_json,
    strict_object,
    verify_health_preview_receipt,
)
from health_api.persistence.models import R5PreviewReservation, R5PreviewWireBinding

R5_PREVIEW_TITLE = "Health preference preview"


@dataclass(frozen=True)
class R5CallerTarget:
    """Offline internal binding fields. The recipient digest covers runtime, model and recipient."""

    pas_owner_id: UUID
    client_id: UUID
    branch_id: UUID
    recipient_digest: str


@dataclass(frozen=True)
class R5VerifiedCallerTarget:
    """Existing PAS principal and registered client from the private authority boundary."""

    pas_owner_id: str
    client_namespace: str
    branch_id: UUID
    recipient_digest: str
    actor: str
    source_epoch: str
    policy_epoch: str


def _create_request(key: UUID) -> dict[str, str]:
    return {"idempotency_key": str(key), "title": R5_PREVIEW_TITLE}


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
    target: R5CallerTarget | R5VerifiedCallerTarget,
    create_request_digest: str | None = None,
    reauthorize: Callable[
        [], tuple[R5SourceAuthority, R5CallerTarget | R5VerifiedCallerTarget] | None
    ],
) -> R5OriginalKeys:
    """Commit both keys and the exact fixed create request before transport.

    Older callers can retain their local reservation, which cannot acquire a wire binding.
    """
    if not re.fullmatch(r"[0-9a-f]{64}", target.recipient_digest):
        raise R5PreviewUnavailable
    if isinstance(target, R5VerifiedCallerTarget):
        if (
            create_request_digest is not None
            or not re.fullmatch(r"usr_[0-9a-f]{32}", target.pas_owner_id)
            or not target.client_namespace
            or len(target.client_namespace) > 200
            or not all(
                0 < len(value) <= 256
                for value in (target.actor, target.source_epoch, target.policy_epoch)
            )
        ):
            raise R5PreviewUnavailable
    elif create_request_digest is None or not re.fullmatch(r"[0-9a-f]{64}", create_request_digest):
        raise R5PreviewUnavailable

    def reauthorize_source() -> R5SourceAuthority | None:
        current = reauthorize()
        if current is None or current[1] != target:
            return None
        return current[0]

    owner_id, source = read_r5_health_preference(
        sessions, settings, request, authority, reauthorize_source
    )
    binding_digest = _binding_digest(
        owner_id, authority, target, source.items[0].permission_dependencies[0].version
    )

    require_current_r5_source_authority(settings, authority, reauthorize_source())
    with sessions() as session, session.begin():
        session.execute(text("SET LOCAL statement_timeout = '1800ms'"))
        if resolve_r5_owner(session, authority) != owner_id:
            raise R5PreviewUnavailable
        proposed_create_key, proposed_preview_key = uuid4(), uuid4()
        proposed_create_digest = create_request_digest or canonical_digest(
            _create_request(proposed_create_key)
        )
        inserted = session.scalars(
            insert(R5PreviewReservation)
            .values(
                [
                    {
                        "original_key": original_key,
                        "owner_id": owner_id,
                        "intent_id": intent_id,
                        "operation": operation,
                        "object_id": authority.selection.object_id,
                        "object_revision": authority.selection.revision,
                        "binding_digest": binding_digest,
                        "request_digest": proposed_create_digest if operation == "create" else None,
                    }
                    for operation, original_key in (
                        ("create", proposed_create_key),
                        ("preview", proposed_preview_key),
                    )
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
        if reservations.keys() != {"create", "preview"} or any(
            row.binding_digest != binding_digest
            or row.object_id != authority.selection.object_id
            or row.object_revision != authority.selection.revision
            for row in reservations.values()
        ):
            raise R5PreviewUnavailable
        create, preview = reservations["create"], reservations["preview"]
        final_digest = create_request_digest or canonical_digest(
            _create_request(create.original_key)
        )
        if create.request_digest != final_digest:
            raise R5PreviewUnavailable
        if isinstance(target, R5VerifiedCallerTarget):
            if inserted:
                _insert_wire_binding(
                    session, create, target.pas_owner_id, final_digest, conversation_id=None
                )
            _require_wire_binding(session, create, target.pas_owner_id, final_digest, None)
        return R5OriginalKeys(create.original_key, preview.original_key)


def _binding_digest(
    owner_id: UUID,
    authority: R5SourceAuthority,
    target: R5CallerTarget | R5VerifiedCallerTarget,
    permission_version: str,
) -> str:
    # Local intent binding is distinct from the accepted wire request digest.
    return hashlib.sha256(
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
                "permission_version": permission_version,
                "pas_owner": str(target.pas_owner_id),
                "client": (
                    target.client_namespace
                    if isinstance(target, R5VerifiedCallerTarget)
                    else str(target.client_id)
                ),
                "branch": str(target.branch_id),
                "recipient": target.recipient_digest,
                "title": R5_PREVIEW_TITLE,
                **(
                    {
                        "actor": target.actor,
                        "source_epoch": target.source_epoch,
                        "policy_epoch": target.policy_epoch,
                    }
                    if isinstance(target, R5VerifiedCallerTarget)
                    else {}
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _insert_wire_binding(
    session: Session,
    reservation: R5PreviewReservation,
    pas_owner_id: str,
    request_digest: str,
    conversation_id: UUID | None,
) -> bool:
    return (
        session.scalar(
            insert(R5PreviewWireBinding)
            .values(
                original_key=reservation.original_key,
                owner_id=reservation.owner_id,
                pas_owner_id=pas_owner_id,
                request_digest=request_digest,
                conversation_id=conversation_id,
            )
            .on_conflict_do_nothing(index_elements=[R5PreviewWireBinding.original_key])
            .returning(R5PreviewWireBinding.original_key)
        )
        is not None
    )


def _require_wire_binding(
    session: Session,
    reservation: R5PreviewReservation,
    pas_owner_id: str,
    request_digest: str,
    conversation_id: UUID | None,
) -> None:
    wire = session.get(R5PreviewWireBinding, reservation.original_key)
    if wire is None or (
        wire.owner_id,
        wire.pas_owner_id,
        wire.request_digest,
        wire.conversation_id,
    ) != (reservation.owner_id, pas_owner_id, request_digest, conversation_id):
        raise R5PreviewUnavailable


def r5_create_request(original: R5OriginalKeys) -> bytes:
    return canonical_json(_create_request(original.create))


def bind_r5_preview_request(
    sessions: sessionmaker[Session],
    settings: Settings,
    *,
    intent_id: UUID,
    source_request: bytes,
    authority: R5SourceAuthority,
    target: R5VerifiedCallerTarget,
    reauthorize: Callable[
        [], tuple[R5SourceAuthority, R5CallerTarget | R5VerifiedCallerTarget] | None
    ],
    original: R5OriginalKeys,
    current_intent: Callable[[R5OriginalKeys], bool],
    create_response: bytes,
    create_receipt: str,
    receipt_keys: Mapping[str, Ed25519PublicKey],
    request: dict[str, Any],
) -> tuple[UUID, str]:
    """Bind the final preview request after verifying create, before the only preview POST."""
    content = request.get("content")
    if (
        set(request) != {"content", "idempotency_key", "choice"}
        or request.get("idempotency_key") != str(original.preview)
        or request.get("choice") != {"mode": "user_owned_plan"}
        or not isinstance(content, str)
        or not 0 < len(content) <= 8192
        or not current_intent(original)
    ):
        raise R5PreviewUnavailable
    try:
        request_digest = canonical_digest(request)
    except (ValueError, UnicodeError):
        raise R5PreviewUnavailable from None
    owner_id = _require_receivable_binding(
        sessions, settings, intent_id, source_request, authority, target, reauthorize, original
    )
    try:
        response = strict_object(create_response, MAX_RESPONSE_BYTES, canonical=False)
        conversation_id = UUID(response["conversation_id"])
        if response != {"conversation_id": str(conversation_id)}:
            raise ValueError("unexpected create response")
        verify_health_preview_receipt(
            create_receipt,
            create_response,
            expected=_receipt_binding(
                owner_id,
                authority,
                target,
                original,
                conversation_id,
                sha256(r5_create_request(original)).hexdigest(),
                purpose="create",
            ),
            keys=receipt_keys,
            now=int(datetime.now(UTC).timestamp()),
        )
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise R5PreviewUnavailable from None
    _require_receivable_binding(
        sessions, settings, intent_id, source_request, authority, target, reauthorize, original
    )
    if not current_intent(original):
        raise R5PreviewUnavailable
    with sessions() as session, session.begin():
        session.execute(text("SET LOCAL statement_timeout = '1800ms'"))
        if resolve_r5_owner(session, authority) != owner_id:
            raise R5PreviewUnavailable
        preview = session.get(R5PreviewReservation, original.preview)
        if preview is None or (preview.owner_id, preview.intent_id, preview.operation) != (
            owner_id,
            intent_id,
            "preview",
        ):
            raise R5PreviewUnavailable
        if not _insert_wire_binding(
            session, preview, target.pas_owner_id, request_digest, conversation_id
        ):
            raise R5PreviewUnavailable
    return conversation_id, request_digest


def _receipt_binding(
    owner_id: UUID,
    authority: R5SourceAuthority,
    target: R5VerifiedCallerTarget,
    original: R5OriginalKeys,
    conversation_id: UUID,
    request_digest: str,
    *,
    purpose: str,
) -> dict[str, object]:
    create = purpose == "create"
    return {
        "schema_version": f"health-application-plan-{purpose}-receipt-v1",
        "purpose": purpose,
        "method": "POST",
        "path": PROFILE_PATH if create else f"{PROFILE_PATH}/{conversation_id}/context-preview",
        "original_key": str(original.create if create else original.preview),
        "original_create_key": str(original.create),
        "request_digest": request_digest,
        "conversation_id": str(conversation_id),
        "target_fingerprint": target.recipient_digest,
        "enrollment_id": str(authority.enrollment_id),
        "enrollment_generation": authority.enrollment_generation,
        "installation_id": str(authority.installation_id),
        "health_owner_id": str(owner_id),
        "pas_owner_id": target.pas_owner_id,
        "actor": target.actor,
        "client_namespace": target.client_namespace,
        "application_id": "health",
        "workspace_id": None,
        "selection": {
            "category": "profile_preferences",
            "object_type": "profile_item",
            "object_id": str(authority.selection.object_id),
            "revision": authority.selection.revision,
            "fields": ["record"],
        },
        "source_epoch": target.source_epoch,
        "policy_epoch": target.policy_epoch,
    }


def _require_receivable_binding(
    sessions: sessionmaker[Session],
    settings: Settings,
    intent_id: UUID,
    source_request: bytes,
    authority: R5SourceAuthority,
    target: R5VerifiedCallerTarget,
    reauthorize: Callable[
        [], tuple[R5SourceAuthority, R5CallerTarget | R5VerifiedCallerTarget] | None
    ],
    original: R5OriginalKeys,
    *,
    preview: tuple[UUID, str] | None = None,
) -> UUID:
    def current() -> R5SourceAuthority | None:
        found = reauthorize()
        return found[0] if found is not None and found[1] == target else None

    owner, projection = read_r5_health_preference(
        sessions, settings, source_request, authority, current
    )
    version = projection.items[0].permission_dependencies[0].version
    binding_digest = _binding_digest(owner, authority, target, version)
    with sessions() as session, session.begin():
        session.execute(text("SET LOCAL statement_timeout = '1800ms'"))
        if resolve_r5_owner(session, authority) != owner:
            raise R5PreviewUnavailable
        for operation, key in (("create", original.create), ("preview", original.preview)):
            row = session.get(R5PreviewReservation, key)
            if row is None or (row.owner_id, row.intent_id, row.operation, row.binding_digest) != (
                owner,
                intent_id,
                operation,
                binding_digest,
            ):
                raise R5PreviewUnavailable
            if operation == "create":
                _require_wire_binding(
                    session,
                    row,
                    target.pas_owner_id,
                    sha256(r5_create_request(original)).hexdigest(),
                    None,
                )
            elif preview is not None:
                conversation_id, request_digest = preview
                _require_wire_binding(
                    session, row, target.pas_owner_id, request_digest, conversation_id
                )
    require_current_r5_source_authority(settings, authority, current())
    return owner


@dataclass(frozen=True)
class R5PreviewEpochs:
    branch_digest: str
    destination: Mapping[str, str]
    source_grants: Mapping[str, str]
    memory_grants: Mapping[str, str]


@dataclass(frozen=True)
class R5PreviewMetadata:
    """Only the bounded inventory category, field names and recipient metadata."""

    history_turns: int
    destination: dict[str, str]
    expires_at: datetime
    source_sensitivity: str = "restricted"


def observe_r5_preview(
    sessions: sessionmaker[Session],
    settings: Settings,
    *,
    intent_id: UUID,
    source_request: bytes,
    authority: R5SourceAuthority,
    target: R5VerifiedCallerTarget,
    original: R5OriginalKeys,
    conversation_id: UUID,
    request_digest: str,
    receipt_keys: Mapping[str, Ed25519PublicKey],
    reauthorize: Callable[
        [], tuple[R5SourceAuthority, R5CallerTarget | R5VerifiedCallerTarget] | None
    ],
    current_epochs: Callable[[UUID], R5PreviewEpochs | None],
    get_status: Callable[[str], tuple[int, bytes, str | None]],
) -> R5PreviewMetadata | None:
    """Attempt only GET of the original preview key; ambiguity stays unknown."""
    binding = (conversation_id, request_digest)
    owner = _require_receivable_binding(
        sessions,
        settings,
        intent_id,
        source_request,
        authority,
        target,
        reauthorize,
        original,
        preview=binding,
    )
    # This independently current dependency must be unavailable on missing or stale authority.
    epochs = current_epochs(original.preview)
    if epochs is None:
        return None
    try:
        status, body, receipt = get_status(
            f"{PROFILE_PATH}/{conversation_id}/context-preview/{original.preview}"
        )
    except (TimeoutError, OSError):
        return None
    if status != 200 or receipt is None:
        return None
    try:
        value = strict_object(body, MAX_RESPONSE_BYTES, canonical=False)
        inventory = value["selected_context"]
        turns = inventory[0]["turns"]
        expires = datetime.fromisoformat(value["expires_at"])
        now = datetime.now(UTC)
        if (
            set(value)
            != {
                "confirmation",
                "destination",
                "purpose",
                "selected_context",
                "input_tokens_estimated",
                "expires_at",
            }
            or value["purpose"] != "foreground_application_plan"
            or type(turns) is not int
            or not 1 <= turns <= 3072
            or type(value["input_tokens_estimated"]) is not int
            or value["input_tokens_estimated"] < 0
            or inventory
            != [
                {"category": "conversation_history", "turns": turns},
                {"category": "ai_memory", "fields": ["content"]},
                {"category": "domain_current", "fields": ["record"]},
            ]
            or value["destination"] != epochs.destination
            or not re.fullmatch(r"[0-9a-f]{64}", value["confirmation"])
            or expires <= now
        ):
            return None
        revision = authority.selection.revision
        claims = verify_health_preview_receipt(
            receipt,
            body,
            keys=receipt_keys,
            now=int(now.timestamp()),
            expected=_receipt_binding(
                owner,
                authority,
                target,
                original,
                conversation_id,
                request_digest,
                purpose="preview",
            )
            | {
                "branch_digest": epochs.branch_digest,
                "actual_revision": revision,
                "permission_version": f"health-object-v1:r{revision}:ai1:cross1",
                "source_sensitivity": "restricted",
                "source_grants": dict(epochs.source_grants),
                "memory_grants": dict(epochs.memory_grants),
                "inventory_digest": canonical_digest(inventory),
                "confirmation": value["confirmation"],
                "destination": dict(epochs.destination),
            },
        )
    except (ValueError, KeyError, TypeError, IndexError, RecursionError):
        return None
    _require_receivable_binding(
        sessions,
        settings,
        intent_id,
        source_request,
        authority,
        target,
        reauthorize,
        original,
        preview=binding,
    )
    if current_epochs(original.preview) != epochs:
        return None
    receipt_expiry = datetime.fromtimestamp(claims["exp"], UTC)
    deadline = min(expires, receipt_expiry)
    if deadline <= datetime.now(UTC):
        return None
    return R5PreviewMetadata(turns, dict(epochs.destination), deadline)
