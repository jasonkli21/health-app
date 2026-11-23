"""An isolated Health caller for the separately enrolled synthetic PAS dispatch profile."""

from __future__ import annotations

import hmac
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from threading import Lock
from time import monotonic
from types import MappingProxyType
from typing import Protocol
from uuid import UUID

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from sqlalchemy import text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from health_api.application.r5_health_caller import (
    R5OriginalKeys,
    R5PreviewEpochs,
    R5PreviewMetadata,
    R5VerifiedCallerTarget,
    bind_r5_preview_request,
    require_current_r5_preview_request,
    verify_r5_create_artifact,
    verify_r5_preview_artifact,
)
from health_api.application.r5_health_source import (
    R5PreviewUnavailable,
    R5SourceAuthority,
    read_r5_health_preference,
    require_r5_test_gate,
    resolve_r5_owner,
)
from health_api.config.settings import Settings
from health_api.integrations.pas_dispatch import (
    MEDIA_TYPE,
    ORIGINAL_KEY_HEADER,
    PREVIEW_HEADER,
    Binding,
    DispatchEvidenceConflict,
    PinnedKey,
    VerifiedPreview,
    digest,
    is_epoch,
    receipt_digest,
    verify_detail,
    verify_preview,
    verify_status,
)
from health_api.integrations.personal_ai_context import HealthContextReadResponse
from health_api.integrations.personal_ai_context_auth import GOOGLE_ISSUERS
from health_api.integrations.personal_ai_preview_receipt import (
    PROFILE_PATH,
    canonical_json,
)
from health_api.persistence.models import HealthDispatchIntent, OwnerErasureLedger

_ORIGINAL_RECEIPT_HEADER = "x-application-plan-receipt"
_PHASES = {"preview", "confirm", "release", "send", "disclose"}


class DispatchUnavailable(ValueError):
    """Uniform denial before exposing any private scope information."""


class DispatchConflict(ValueError):
    """An authorized original-key intent has different committed bytes."""


class DispatchExpired(ValueError):
    """The authenticated confirmation expired."""


@dataclass(frozen=True)
class Principal:
    issuer: str
    subject: str


@dataclass(frozen=True)
class Enrollment:
    enrollment_id: UUID
    generation: int
    health_owner: UUID
    firebase: Principal
    pas_human: Principal
    pas_owner: str
    installation: str
    client: str
    tenant: str
    target: str
    application: str = "health"
    purpose: str = "personal_ai_context"
    workspace: None = None
    active: bool = True


@dataclass(frozen=True)
class LiveAuthority:
    """Trusted, independently obtained synthetic identity and recipient witnesses."""

    service: Principal
    service_audience: str
    firebase_revocation_checked: bool
    foreground: bool
    pas_human: Principal
    pas_scope: R5VerifiedCallerTarget
    source: R5SourceAuthority
    enrollments: tuple[Enrollment, ...]
    preview_epochs: R5PreviewEpochs
    consent_epoch: int
    erasure_epoch: int
    recipient_source_grant: bool
    recipient_memory_grant: bool
    source_sensitivity_ceiling: str
    memory_commitment: str
    destination_commitment: str
    continuity_generation: int


@dataclass(frozen=True)
class PrivatePreview:
    """References to the original R5 scope and independently assembled dispatch binding."""

    intent_id: UUID
    source_request: bytes
    authority: R5SourceAuthority
    target: R5VerifiedCallerTarget
    original: R5OriginalKeys
    conversation: UUID
    preview_request_digest: str
    binding: Binding


@dataclass(frozen=True)
class OriginalReceipt:
    digest: str
    response_digest: str
    version: str
    signer: str
    kid: str


@dataclass(frozen=True)
class ReviewedPreview:
    scope: PrivatePreview
    metadata: R5PreviewMetadata
    preview: VerifiedPreview
    create: OriginalReceipt
    original_preview: OriginalReceipt
    deadline: int


@dataclass(frozen=True)
class ContinuityRecord:
    original_key: UUID
    binding_digest: str
    body_digest: str
    generation: int


class ContinuityWitness(Protocol):
    """Independent fixture checkpoint. Missing or uncertain continuity denies the operation."""

    def current(self, generation: int, record: ContinuityRecord | None) -> bool: ...

    def reserve(self, record: ContinuityRecord) -> bool:
        """Irreversibly consume this key before native insertion, returning one winner."""
        ...


@dataclass(frozen=True)
class FixtureResponse:
    status: int
    raw: bytes
    # Preserve header multiplicity across the fixture boundary.
    headers: tuple[tuple[str, str], ...] = ()

    def is_private_response(self) -> bool:
        return (
            self.status == 200
            and self.header("content-type") == MEDIA_TYPE
            and self.header("cache-control") == "no-store"
        )

    def header(self, name: str) -> str:
        values = [value for key, value in self.headers if key.lower() == name.lower()]
        if len(values) != 1:
            raise DispatchUnavailable
        return values[0]


class FixtureTransport(Protocol):
    """Pinned fixture channel adding app authentication and the original R5 operation proof."""

    def post(self, path: str, headers: Mapping[str, str], body: bytes) -> FixtureResponse: ...

    def get(self, path: str, headers: Mapping[str, str]) -> FixtureResponse: ...


def source_commitment(
    key: bytes,
    projection: HealthContextReadResponse,
    enrollment: Enrollment,
    consent_epoch: int,
    erasure_epoch: int,
) -> str:
    """Keep the exact authorized projection and low-entropy source data in Health."""
    return hmac.digest(
        key,
        canonical_json(
            {
                "profile": projection.model_dump(mode="json"),
                "owner": str(enrollment.health_owner),
                "enrollment": str(enrollment.enrollment_id),
                "enrollment_version": enrollment.generation,
                "consent_epoch": consent_epoch,
                "erasure_epoch": erasure_epoch,
                "lifecycle": "active",
            }
        ),
        "sha256",
    ).hex()


class HealthDispatchCaller:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        settings: Settings,
        *,
        current_authority: Callable[[], LiveAuthority | None],
        current_intent: Callable[[R5OriginalKeys], bool],
        original_keys: Mapping[str, Ed25519PublicKey],
        preview_key: PinnedKey,
        terminal_key: PinnedKey,
        projection_key: bytes,
        witness: ContinuityWitness,
        transport: FixtureTransport,
        now: Callable[[], int],
    ) -> None:
        try:
            require_r5_test_gate(settings)
        except R5PreviewUnavailable:
            raise DispatchUnavailable from None
        if (
            not settings.personal_ai_health_dispatch_test_enabled
            or len(projection_key) < 32
            or preview_key.purpose != "preview"
            or preview_key.audience != "health"
            or terminal_key.purpose != "terminal"
            or terminal_key.audience != preview_key.issuer
            or terminal_key.key.public_bytes_raw() == preview_key.key.public_bytes_raw()
        ):
            raise DispatchUnavailable
        self._sessions = sessions
        self._settings = settings
        self._authority = current_authority
        self._current_intent = current_intent
        self._original_keys = dict(original_keys)
        self._preview_key = preview_key
        self._terminal_key = terminal_key
        self._projection_key = projection_key
        self._witness = witness
        self._transport = transport
        self._now = now
        self._nonce_lock = Lock()
        self._nonces: set[UUID] = set()
        self._preview_lock = Lock()
        self._prepared: dict[UUID, ReviewedPreview] = {}

    def _require_current(self, scope: PrivatePreview) -> tuple[UUID, LiveAuthority]:
        try:
            return self._read_authority(scope)
        except (DispatchUnavailable, OSError, SQLAlchemyError):
            self.abandon(scope.original.preview)
            raise DispatchUnavailable from None

    def _read_authority(self, scope: PrivatePreview) -> tuple[UUID, LiveAuthority]:
        current = self._authority()
        expect = scope.binding.fields
        destination = expect["destination"]
        if current is None or (
            current.service.issuer not in GOOGLE_ISSUERS
            or current.service.subject != self._settings.personal_ai_context_service_account
            or current.service_audience != self._settings.personal_ai_context_service_audience
            or current.firebase_revocation_checked is not True
            or current.foreground is not True
            or current.pas_scope != scope.target
            or (current.pas_human.issuer, current.pas_human.subject)
            != (expect["actor_issuer"], expect["subject"])
            or (
                expect["app"],
                expect["workspace"],
                expect["owner"],
                expect["client"],
                expect["policy"],
                expect["conversation"],
                expect["create_key"],
                expect["original_key"],
            )
            != (
                "health",
                None,
                scope.target.pas_owner_id,
                scope.target.client_namespace,
                scope.target.policy_epoch,
                str(scope.conversation),
                str(scope.original.create),
                str(scope.original.preview),
            )
            or scope.original.create == scope.original.preview
            or current.recipient_source_grant is not True
            or current.recipient_memory_grant is not True
            or current.source_sensitivity_ceiling != "restricted"
            or not is_epoch(current.erasure_epoch)
            or not is_epoch(current.consent_epoch)
            or not is_epoch(current.continuity_generation)
            or current.continuity_generation == 0
            or expect["epoch"] != current.consent_epoch
            or expect["memory"] != current.memory_commitment
            or expect["branch"] != current.preview_epochs.branch_digest
            or destination["provider"] != "fake"
            or destination["model"] != "fake"
            or destination["endpoint"] != "loopback-fixture"
            or current.destination_commitment != digest(canonical_json(destination))
        ):
            raise DispatchUnavailable
        current_epochs = current.preview_epochs.snapshot()
        if dict(current_epochs.destination) != {
            "application": "health",
            "provider": destination["provider"],
            "model": destination["model"],
            "runtime": f"local:{destination['runtime']}",
            "recipient": f"openai-responses:{destination['account']}",
        }:
            raise DispatchUnavailable
        firebase = Principal(current.source.identity.issuer, current.source.identity.subject)
        candidates = [
            link
            for link in current.enrollments
            if link.active
            and (link.application, link.workspace, link.purpose)
            == ("health", None, "personal_ai_context")
            and (link.firebase == firebase or link.pas_human == current.pas_human)
        ]
        if len(candidates) != 1:
            raise DispatchUnavailable
        link = candidates[0]
        if (
            link.firebase != firebase
            or link.pas_human != current.pas_human
            or (
                link.pas_owner,
                link.installation,
                link.client,
                link.tenant,
                link.target,
                link.enrollment_id,
                link.generation,
            )
            != (
                expect["owner"],
                expect["installation"],
                expect["client"],
                expect["tenant"],
                expect["target"],
                scope.authority.enrollment_id,
                scope.authority.enrollment_generation,
            )
            or link.installation != str(scope.authority.installation_id)
            or not self._witness.current(current.continuity_generation, None)
        ):
            raise DispatchUnavailable

        def fresh_source() -> R5SourceAuthority | None:
            latest = self._authority()
            if (
                latest != current
                or latest is None
                or latest.preview_epochs.snapshot() != current_epochs
            ):
                return None
            return latest.source

        def reauthorize() -> tuple[R5SourceAuthority, R5VerifiedCallerTarget] | None:
            authority = fresh_source()
            return None if authority is None else (authority, scope.target)

        try:
            owner, projection = read_r5_health_preference(
                self._sessions, self._settings, scope.source_request, scope.authority, fresh_source
            )
            require_current_r5_preview_request(
                self._sessions,
                self._settings,
                intent_id=scope.intent_id,
                source_request=scope.source_request,
                authority=scope.authority,
                target=scope.target,
                reauthorize=reauthorize,
                original=scope.original,
                conversation_id=scope.conversation,
                request_digest=scope.preview_request_digest,
                current_intent=self._current_intent,
            )
            with self._sessions() as session:
                if session.get(OwnerErasureLedger, owner) is not None:
                    raise DispatchUnavailable
        except R5PreviewUnavailable:
            raise DispatchUnavailable from None
        if (
            owner != link.health_owner
            or not hmac.compare_digest(
                expect["source"],
                source_commitment(
                    self._projection_key,
                    projection,
                    link,
                    current.consent_epoch,
                    current.erasure_epoch,
                ),
            )
            or fresh_source() is None
            or not self._witness.current(current.continuity_generation, None)
        ):
            raise DispatchUnavailable
        return owner, current

    def registered_source(
        self, resolve: Callable[[UUID, UUID], PrivatePreview | None]
    ) -> Callable[[bytes, str, str], dict[str, object]]:
        """Resolve the original R5 scope in Health for each authenticated PAS callback."""

        def current(binding_bytes: bytes, phase: str, nonce: str) -> dict[str, object]:
            binding = Binding(binding_bytes)
            fields = binding.fields
            key = UUID(nonce)
            if str(key) != nonce:
                raise DispatchUnavailable
            scope = resolve(UUID(fields["conversation"]), UUID(fields["original_key"]))
            if scope is None:
                raise DispatchUnavailable
            expected = scope.binding.fields
            # At preview the independently reserved scope has no PAS receipt yet.
            if phase == "preview":
                expected["preview_receipt"] = fields["preview_receipt"]
            if expected != fields:
                raise DispatchUnavailable
            return self.current(replace(scope, binding=binding), phase, key)

        return current

    def current(self, scope: PrivatePreview, phase: str, nonce: UUID) -> dict[str, object]:
        """The trusted, registered in-process reverse callback never returns source data."""
        started_at = monotonic()
        start = self._now()
        with self._nonce_lock:
            if phase not in _PHASES or nonce in self._nonces or len(self._nonces) >= 8192:
                raise DispatchUnavailable
            self._nonces.add(nonce)
        try:
            owner, authority = self._require_current(scope)
            if phase != "preview":
                row = self._load(scope, owner)
                if row is None or not self._witness.current(
                    authority.continuity_generation,
                    ContinuityRecord(
                        scope.original.preview,
                        row.binding_digest,
                        row.body_digest,
                        row.continuity_generation,
                    ),
                ):
                    raise DispatchUnavailable
        except DispatchUnavailable:
            allowed = False
        else:
            allowed = self._now() == start and monotonic() - started_at < 1
        return {
            "binding_sha256": scope.binding.sha256,
            "phase": phase,
            "nonce": str(nonce),
            "current": allowed,
            "expires": start + 1,
        }

    def acquire_preview(
        self,
        scope: PrivatePreview,
        *,
        content: str,
        create_response: bytes,
        create_header: str,
    ) -> ReviewedPreview:
        """Bind and submit one private preview, retaining the original R5 proof."""
        request = {
            "content": content,
            "idempotency_key": str(scope.original.preview),
            "choice": {"mode": "user_owned_plan"},
        }
        body = canonical_json(request)
        if digest(body) != scope.preview_request_digest:
            raise DispatchUnavailable
        live = self._authority()

        def reauthorize() -> tuple[R5SourceAuthority, R5VerifiedCallerTarget] | None:
            current = self._authority()
            if current is None or current != live or current.pas_scope != scope.target:
                return None
            return current.source, current.pas_scope

        try:
            if receipt_digest(create_header) != scope.binding.fields["create_receipt"]:
                raise DispatchUnavailable
            conversation, _ = bind_r5_preview_request(
                self._sessions,
                self._settings,
                intent_id=scope.intent_id,
                source_request=scope.source_request,
                authority=scope.authority,
                target=scope.target,
                reauthorize=reauthorize,
                original=scope.original,
                current_intent=self._current_intent,
                create_response=create_response,
                create_receipt=create_header,
                receipt_keys=self._original_keys,
                request=request,
            )
            if conversation != scope.conversation:
                raise DispatchUnavailable
            self._require_current(scope)
            reply = self._transport.post(
                f"{PROFILE_PATH}/{scope.conversation}/context-preview",
                {
                    "Accept": MEDIA_TYPE,
                    "Content-Type": MEDIA_TYPE,
                    "X-Application-ID": "health",
                },
                body,
            )
            if not reply.is_private_response():
                raise DispatchUnavailable
            preview_header = reply.header(_ORIGINAL_RECEIPT_HEADER)
            fields = scope.binding.fields
            fields["preview_receipt"] = receipt_digest(preview_header)
            reviewed_scope = replace(scope, binding=Binding(canonical_json(fields)))
            return self.prepare(
                reviewed_scope,
                create_response=create_response,
                create_header=create_header,
                preview_response=reply.raw,
                preview_header=preview_header,
                dispatch_envelope=reply.header(PREVIEW_HEADER).encode("ascii"),
            )
        except (ValueError, OSError, EOFError):
            raise DispatchUnavailable from None

    def prepare(
        self,
        scope: PrivatePreview,
        *,
        create_response: bytes,
        create_header: str,
        preview_response: bytes,
        preview_header: str,
        dispatch_envelope: bytes,
    ) -> ReviewedPreview:
        """Adopt only live signatures and the authorized R5 inventory, without any journal write."""
        owner, live = self._require_current(scope)
        expect = scope.binding.fields
        now = self._now()
        try:
            conversation, create = verify_r5_create_artifact(
                owner,
                scope.authority,
                scope.target,
                scope.original,
                create_response,
                create_header,
                self._original_keys,
                now,
            )
            metadata, preview = verify_r5_preview_artifact(
                owner,
                scope.authority,
                scope.target,
                scope.original,
                scope.conversation,
                scope.preview_request_digest,
                live.preview_epochs.snapshot(),
                preview_response,
                preview_header,
                self._original_keys,
                datetime.fromtimestamp(now, UTC),
            )
            if (
                conversation != scope.conversation
                or receipt_digest(create_header) != expect["create_receipt"]
                or receipt_digest(preview_header) != expect["preview_receipt"]
            ):
                raise DispatchUnavailable
            verified = verify_preview(dispatch_envelope, scope.binding, self._preview_key, now)
            # Limit the preparation to the earliest signed authorization deadline.
            deadline = min(verified.expires, int(metadata.expires_at.timestamp()), create["exp"])
            create_proof = OriginalReceipt(
                expect["create_receipt"],
                create["response_digest"],
                create["schema_version"],
                create["iss"],
                create["kid"],
            )
            preview_proof = OriginalReceipt(
                expect["preview_receipt"],
                preview["response_digest"],
                preview["schema_version"],
                preview["iss"],
                preview["kid"],
            )
        except (ValueError, TypeError, RecursionError, OverflowError):
            raise DispatchUnavailable from None
        self._require_current(scope)
        if self._now() >= deadline:
            raise DispatchUnavailable
        metadata = replace(metadata, destination=MappingProxyType(dict(metadata.destination)))
        selection = ReviewedPreview(
            scope, metadata, verified, create_proof, preview_proof, deadline
        )
        with self._preview_lock:
            self._prepared = {
                key: item for key, item in self._prepared.items() if item.deadline > self._now()
            }
            existing = self._prepared.get(scope.original.preview)
            if existing is not None and existing != selection:
                raise DispatchUnavailable
            if len(self._prepared) >= 64 and existing is None:
                self._prepared.pop(next(iter(self._prepared)))
            self._prepared[scope.original.preview] = selection
        return selection

    def abandon(self, original_key: UUID) -> None:
        """Evict the process-local preview and confirmation on session end or revocation."""
        with self._preview_lock:
            self._prepared.pop(original_key, None)

    def _load(self, scope: PrivatePreview, owner: UUID) -> HealthDispatchIntent | None:
        with self._sessions() as session:
            row = session.get(HealthDispatchIntent, scope.original.preview)
            if row is not None:
                fields = scope.binding.fields
                if (
                    row.quarantined_at is not None
                    or row.owner_id != owner
                    or row.create_key != scope.original.create
                    or row.conversation_id != scope.conversation
                    or str(row.attempt) != fields["attempt"]
                    or str(row.root) != fields["root"]
                    or row.binding_digest != scope.binding.sha256
                    or row.create_receipt_digest != fields["create_receipt"]
                    or row.preview_receipt_digest != fields["preview_receipt"]
                ):
                    raise DispatchUnavailable
                session.expunge(row)
            return row

    def _record(
        self,
        scope: PrivatePreview,
        owner: UUID,
        reviewed: ReviewedPreview,
        record: ContinuityRecord,
    ) -> bool:
        fields = scope.binding.fields
        create, preview = reviewed.create, reviewed.original_preview
        try:
            with self._sessions() as session, session.begin():
                session.execute(text("SET LOCAL statement_timeout = '1800ms'"))
                if resolve_r5_owner(session, scope.authority) != owner:
                    raise DispatchUnavailable
                return (
                    session.execute(
                        insert(HealthDispatchIntent)
                        .values(
                            original_key=record.original_key,
                            create_key=scope.original.create,
                            owner_id=owner,
                            conversation_id=scope.conversation,
                            attempt=UUID(fields["attempt"]),
                            root=UUID(fields["root"]),
                            binding_digest=record.binding_digest,
                            body_digest=record.body_digest,
                            confirmation_digest=reviewed.preview.claims_digest,
                            create_receipt_digest=create.digest,
                            create_response_digest=create.response_digest,
                            create_version=create.version,
                            create_signer=create.signer,
                            create_kid=create.kid,
                            preview_receipt_digest=preview.digest,
                            preview_response_digest=preview.response_digest,
                            preview_version=preview.version,
                            preview_signer=preview.signer,
                            preview_kid=preview.kid,
                            continuity_generation=record.generation,
                        )
                        .on_conflict_do_nothing(
                            index_elements=[HealthDispatchIntent.original_key],
                        )
                        .returning(HealthDispatchIntent.original_key)
                    ).scalar_one_or_none()
                    is not None
                )
        except (SQLAlchemyError, R5PreviewUnavailable):
            raise DispatchUnavailable from None

    def confirm(self, reviewed: ReviewedPreview, confirmed_bytes: bytes) -> None:
        """An explicit foreground action submits once, without adopting any POST response."""
        scope = reviewed.scope
        owner, live = self._require_current(scope)
        body = reviewed.preview.confirmation_body
        if not hmac.compare_digest(confirmed_bytes, body):
            raise DispatchConflict
        record = ContinuityRecord(
            scope.original.preview, scope.binding.sha256, digest(body), live.continuity_generation
        )
        if self._now() >= reviewed.deadline:
            self.abandon(scope.original.preview)
            raise DispatchExpired
        with self._preview_lock:
            prepared = self._prepared.get(scope.original.preview) is reviewed
        existing = self._load(scope, owner)
        if existing is not None:
            if existing.body_digest != record.body_digest:
                raise DispatchConflict
            if not self._witness.current(record.generation, record):
                raise DispatchUnavailable
            return
        if not prepared:
            raise DispatchUnavailable
        if not self._witness.reserve(record):
            return  # Followers may recover through observe; none may reuse an absent winner.
        if not self._record(scope, owner, reviewed, record):
            return
        self.abandon(scope.original.preview)
        owner, current = self._require_current(scope)
        persisted = self._load(scope, owner)
        if (
            self._now() >= reviewed.deadline
            or not self._preview_key.active()
            or persisted is None
            or persisted.body_digest != digest(body)
            or current.continuity_generation != record.generation
            or not self._witness.current(record.generation, record)
        ):
            raise DispatchUnavailable
        try:
            self._transport.post(
                f"{PROFILE_PATH}/{scope.conversation}/continue",
                {
                    "Accept": MEDIA_TYPE,
                    "Content-Type": MEDIA_TYPE,
                    "X-Application-ID": "health",
                },
                body,
            )
        except (OSError, TimeoutError, EOFError):
            pass  # The irrevocable committed intent can only be observed through GET.

    def observe(self, scope: PrivatePreview) -> str | None:
        """Recover by original-key GET and release only the matching authenticated detail."""
        owner, live = self._require_current(scope)
        row = self._load(scope, owner)
        if row is None:
            return None
        record = ContinuityRecord(
            scope.original.preview,
            scope.binding.sha256,
            row.body_digest,
            row.continuity_generation,
        )

        def current() -> bool:
            active_owner, authority = self._require_current(scope)
            found = self._load(scope, active_owner)
            return (
                active_owner == owner
                and authority.continuity_generation
                == live.continuity_generation
                == record.generation
                and found is not None
                and found.body_digest == row.body_digest
                and self._witness.current(record.generation, record)
                and self._terminal_key.active()
            )

        headers = {"Accept": MEDIA_TYPE, "X-Application-ID": "health"}
        if not current():
            raise DispatchUnavailable
        try:
            response = self._transport.get(
                f"/v1/conversations/{scope.conversation}/continuations/{scope.original.preview}",
                headers,
            )
            if not response.is_private_response() or not current():
                return None
            terminal = verify_status(
                response.raw,
                binding=scope.binding,
                body_digest=row.body_digest,
                trust=self._terminal_key,
                now=self._now(),
            )
            if terminal is None or not current():
                return None
            detail = self._transport.get(
                f"/v1/conversations/{scope.conversation}",
                headers | {ORIGINAL_KEY_HEADER: str(scope.original.preview)},
            )
            if not detail.is_private_response() or not current():
                return None
            result = verify_detail(detail.raw, scope.binding, terminal)
            if not current():
                return None
            if self._now() >= terminal.expires:
                raise DispatchEvidenceConflict("dispatch terminal expired")
            return result
        except DispatchEvidenceConflict:
            self._quarantine(owner, record)
        except (ValueError, OSError, TimeoutError, EOFError, TypeError, RecursionError):
            pass
        return None

    def _quarantine(self, owner: UUID, record: ContinuityRecord) -> None:
        try:
            with self._sessions() as session, session.begin():
                session.execute(
                    update(HealthDispatchIntent)
                    .where(
                        HealthDispatchIntent.owner_id == owner,
                        HealthDispatchIntent.original_key == record.original_key,
                        HealthDispatchIntent.binding_digest == record.binding_digest,
                        HealthDispatchIntent.body_digest == record.body_digest,
                        HealthDispatchIntent.quarantined_at.is_(None),
                    )
                    .values(quarantined_at=datetime.fromtimestamp(self._now(), UTC))
                )
        except SQLAlchemyError:
            # Owner deletion can revoke the intent concurrently.
            pass
