"""Offline Health source slice for the R5 dual-proof candidate."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from health_api.application.personal_ai_context import (
    HealthContextSelectionError,
    _content_fingerprint,
    read_personal_ai_health_context,
    resolve_existing_owner,
)
from health_api.config.settings import Settings
from health_api.integrations.firebase_auth import VerifiedIdentity
from health_api.integrations.personal_ai_context import (
    HEALTH_CONTEXT_MAX_BYTES,
    HealthContextEntityReference,
    HealthContextPermissionVersion,
    HealthContextReadRequest,
    HealthContextReadResponse,
)

# Synthetic comparison fixture only. Neither these literals nor this module register a PAS
# source or authorize a production read.
_SYNTHETIC_RECORD = {
    "kind": "preference",
    "category": "preferences",
    "key": "r5_synthetic_presentation_format",
    "label": "Synthetic presentation format",
    "value": {"type": "text", "value": "bullets"},
}


class R5PreviewUnavailable(ValueError):
    """The requested preview cannot be used or published."""


@dataclass(frozen=True)
class R5HealthSelection:
    object_id: UUID
    revision: int

    def __post_init__(self) -> None:
        if type(self.revision) is not int or self.revision < 1:
            raise ValueError("Invalid selection revision")


@dataclass(frozen=True)
class R5SourceAuthority:
    """Live result expected from the future C1 boundary, never parsed from requests."""

    identity: VerifiedIdentity
    enrollment_id: UUID
    enrollment_generation: int
    installation_id: UUID
    selection: R5HealthSelection


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise ValueError("Duplicate JSON member")
    return fields


def parse_r5_source_request(raw: bytes, selection: R5HealthSelection) -> HealthContextReadRequest:
    if len(raw) > HEALTH_CONTEXT_MAX_BYTES:
        raise R5PreviewUnavailable
    try:
        decoded = json.loads(raw, object_pairs_hook=_unique_object)
        if (
            not isinstance(decoded, dict)
            or not {"schema_version", "application_id", "workspace_id", "purpose"} <= decoded.keys()
        ):
            raise ValueError("Missing scope")
        request = HealthContextReadRequest.model_validate_json(raw)
    except (ValueError, RecursionError):
        raise R5PreviewUnavailable from None

    if (
        request.operation != "profile"
        or request.category != "profile_preferences"
        or request.entity_refs
        != (
            HealthContextEntityReference(object_type="profile_item", object_id=selection.object_id),
        )
        or request.fields != ("record",)
        or request.max_results != 1
    ):
        raise R5PreviewUnavailable
    return request


def require_r5_test_gate(settings: Settings) -> None:
    if not (
        settings.personal_ai_r5_preview_enabled
        and settings.personal_ai_context_read_enabled
        and settings.app_env == "test"
        and settings.auth_mode == "firebase"
        and settings.firebase_project_id
    ):
        raise R5PreviewUnavailable


def require_current_r5_source_authority(
    settings: Settings,
    authority: R5SourceAuthority,
    current: R5SourceAuthority | None,
) -> None:
    # The offline boundary applies a conservative fixture lifetime. Freeze real timing
    # and routing under C1 before adding a live caller of this function.
    if current is None:
        raise R5PreviewUnavailable
    identity = current.identity
    now_seconds = int(datetime.now(UTC).timestamp())
    max_age = settings.personal_ai_context_user_token_max_age_seconds
    if (
        identity.issuer != f"https://securetoken.google.com/{settings.firebase_project_id}"
        or not identity.subject
        or type(identity.auth_time) is not int
        or type(identity.issued_at) is not int
        or not now_seconds - max_age <= identity.auth_time <= identity.issued_at <= now_seconds
        or identity.auth_time != authority.identity.auth_time
        or (identity.issuer, identity.subject)
        != (authority.identity.issuer, authority.identity.subject)
        or current.enrollment_id != authority.enrollment_id
        or type(current.enrollment_generation) is not int
        or current.enrollment_generation < 1
        or current.enrollment_generation != authority.enrollment_generation
        or current.installation_id != authority.installation_id
        or current.selection != authority.selection
    ):
        raise R5PreviewUnavailable


def resolve_r5_owner(session: Session, authority: R5SourceAuthority) -> UUID:
    owner_id = resolve_existing_owner(
        session, issuer=authority.identity.issuer, subject=authority.identity.subject
    )
    if owner_id is None:
        raise R5PreviewUnavailable
    return owner_id


def read_r5_health_preference(
    sessions: sessionmaker[Session],
    settings: Settings,
    raw: bytes,
    authority: R5SourceAuthority,
    reauthorize: Callable[[], R5SourceAuthority | None],
) -> tuple[UUID, HealthContextReadResponse]:
    """Read one exact synthetic fixture using fresh snapshots and a private live authority seam.

    The seam has no deployed implementation. A caller must establish the independently
    authenticated PAS service, enrollment and Firebase proof before making it available.
    """
    require_r5_test_gate(settings)
    request = parse_r5_source_request(raw, authority.selection)
    require_current_r5_source_authority(settings, authority, reauthorize())

    try:
        with sessions() as session, session.begin():
            session.execute(text("SET TRANSACTION READ ONLY"))
            session.execute(text("SET LOCAL statement_timeout = '1800ms'"))
            owner_id = resolve_r5_owner(session, authority)
            projection = read_personal_ai_health_context(session, owner_id, request)
        if projection.truncated or len(projection.items) != 1:
            raise R5PreviewUnavailable
        item = projection.items[0]
        version = f"health-object-v1:r{authority.selection.revision}:ai1:cross1"
        dependency = item.permission_dependencies[0]
        fingerprint = _content_fingerprint(item.payload)
        if (
            item.object_id != authority.selection.object_id
            or item.object_revision != authority.selection.revision
            or item.source_kind != "manual"
            or item.confirmation_status != "user_confirmed"
            or set(item.payload.model_dump(exclude_none=True))
            != {"category", "object_type", "record"}
            or item.payload.record != _SYNTHETIC_RECORD
            or tuple((field.field, field.sensitivity) for field in item.field_sensitivity)
            != (("record", "restricted"),)
            or {(ref.kind, ref.reference_id, ref.fingerprint) for ref in item.source_refs}
            != {
                ("record", str(item.object_id), fingerprint),
                ("source", str(item.source_id), fingerprint),
            }
            or dependency.permission_id
            != f"health_context_read:profile_preferences:profile_item:{item.object_id}"
            or dependency.version != version
        ):
            raise R5PreviewUnavailable

        require_current_r5_source_authority(settings, authority, reauthorize())
        verify_request = HealthContextReadRequest(
            operation="verify",
            category="profile_preferences",
            max_results=1,
            entity_refs=request.entity_refs,
            fields=("permission_version",),
            max_bytes=request.max_bytes,
        )
        with sessions() as session, session.begin():
            session.execute(text("SET TRANSACTION READ ONLY"))
            session.execute(text("SET LOCAL statement_timeout = '1800ms'"))
            if resolve_r5_owner(session, authority) != owner_id:
                raise R5PreviewUnavailable
            verified = read_personal_ai_health_context(session, owner_id, verify_request)
        if verified.truncated or verified.permission_versions != (
            HealthContextPermissionVersion(object_id=item.object_id, version=version),
        ):
            raise R5PreviewUnavailable
        require_current_r5_source_authority(settings, authority, reauthorize())
        return owner_id, projection
    except HealthContextSelectionError:
        raise R5PreviewUnavailable from None
