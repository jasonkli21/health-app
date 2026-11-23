from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Lock
from typing import Any
from uuid import UUID, uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import Engine, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker
from test_r5_health_preview import make_authority, seed_owner, seed_profile, wire

from health_api.application.account_data_service import (
    begin_owner_deletion,
    export_owner_snapshot,
    process_owner_deletion,
)
from health_api.application.health_dispatch import (
    ContinuityRecord,
    DispatchConflict,
    DispatchExpired,
    DispatchUnavailable,
    Enrollment,
    FixtureResponse,
    HealthDispatchCaller,
    LiveAuthority,
    Principal,
    PrivatePreview,
    source_commitment,
)
from health_api.application.profile_service import update_profile_item
from health_api.application.r5_health_caller import (
    R5PreviewEpochs,
    R5VerifiedCallerTarget,
    _receipt_binding,
    bind_r5_preview_request,
    r5_create_request,
    reserve_r5_operation_keys,
)
from health_api.application.r5_health_source import read_r5_health_preference
from health_api.config.settings import Settings
from health_api.integrations.object_storage import LocalObjectStorage
from health_api.integrations.pas_dispatch import (
    MEDIA_TYPE,
    ORIGINAL_KEY_HEADER,
    PREVIEW_HEADER,
    VERSION,
    Binding,
    PinnedKey,
    digest,
    receipt_digest,
)
from health_api.integrations.personal_ai_preview_receipt import (
    RECEIPT_AUDIENCE,
    RECEIPT_ISSUER,
    canonical_json,
)
from health_api.persistence.models import HealthDispatchIntent

PROJECTION_KEY = b"synthetic-health-projection-key-for-tests"


def encoded(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def signed_header(claims: dict[str, object], body: bytes, now: int, key: Ed25519PrivateKey) -> str:
    raw = canonical_json(
        claims
        | {
            "alg": "Ed25519",
            "kid": "old-r5",
            "iss": RECEIPT_ISSUER,
            "aud": RECEIPT_AUDIENCE,
            "iat": now,
            "exp": now + 30,
            "response_digest": digest(body),
        }
    )
    return f"{encoded(raw)}.{encoded(key.sign(raw))}"


class TestWitness:
    __test__ = False

    def __init__(self) -> None:
        self.generation = 1
        self.records: dict[UUID, ContinuityRecord] = {}
        self.lock = Lock()
        self.available = True

    def current(self, generation: int, record: ContinuityRecord | None) -> bool:
        with self.lock:
            return (
                self.available
                and self.generation == generation
                and (record is None or self.records.get(record.original_key) == record)
            )

    def reserve(self, record: ContinuityRecord) -> bool:
        with self.lock:
            if not self.available or record.generation != self.generation:
                return False
            if record.original_key in self.records:
                return False
            self.records[record.original_key] = record
            return True


class RecordingTransport:
    def __init__(self, sessions: sessionmaker[Session], scope: PrivatePreview) -> None:
        self.posts: list[tuple[str, str, bytes]] = []
        self.gets: list[tuple[str, Mapping[str, str]]] = []
        self.sessions = sessions
        self.scope = scope
        self.replies: list[FixtureResponse] = []
        self.post_failure: Exception | None = None
        self.after_status = lambda: None
        self.after_detail = lambda: None
        self.preview = lambda: FixtureResponse(404, b"")

    def post(self, path: str, headers: Mapping[str, str], body: bytes) -> FixtureResponse:
        assert headers == {
            "Accept": MEDIA_TYPE,
            "Content-Type": MEDIA_TYPE,
            "X-Application-ID": "health",
        }
        self.posts.append((path, headers["Content-Type"], body))
        if path.endswith("/context-preview"):
            return self.preview()
        with self.sessions() as session:
            row = session.get(HealthDispatchIntent, self.scope.original.preview)
            assert row and row.body_digest == digest(body) and row.submitted_at
        if self.post_failure is not None:
            raise self.post_failure
        return FixtureResponse(202, b"")

    def get(self, path: str, headers: Mapping[str, str]) -> FixtureResponse:
        self.gets.append((path, dict(headers)))
        if path.endswith(str(self.scope.original.preview)):
            assert ORIGINAL_KEY_HEADER not in headers
            self.after_status()
        else:
            assert headers[ORIGINAL_KEY_HEADER] == str(self.scope.original.preview)
            self.after_detail()
        return self.replies.pop(0) if self.replies else FixtureResponse(404, b"")


@dataclass
class Case:
    settings: Settings
    sessions: sessionmaker[Session]
    scope: PrivatePreview
    live: LiveAuthority | None
    owner: UUID
    now: int
    witness: TestWitness
    transport: RecordingTransport
    artifacts: dict[str, Any]
    old_key: Ed25519PrivateKey
    pas: Ed25519PrivateKey
    runtime: Ed25519PrivateKey
    key_active: bool = True

    def caller(self) -> HealthDispatchCaller:
        return HealthDispatchCaller(
            self.sessions,
            self.settings,
            current_authority=lambda: self.live,
            current_intent=lambda original: original == self.scope.original,
            original_keys={"old-r5": self.old_key.public_key()},
            preview_key=PinnedKey(
                "pas", "preview", "health", "p1", self.pas.public_key(), lambda: self.key_active
            ),
            terminal_key=PinnedKey(
                "runtime",
                "terminal",
                "pas",
                "r1",
                self.runtime.public_key(),
                lambda: self.key_active,
            ),
            projection_key=PROJECTION_KEY,
            witness=self.witness,
            transport=self.transport,
            now=lambda: self.now,
        )


@pytest.fixture
def case(db_session: Session, postgres_engine: Engine, request: pytest.FixtureRequest) -> Case:
    settings = Settings(
        app_env="test",
        auth_mode="firebase",
        firebase_project_id="health-test",
        personal_ai_context_service_audience="https://health.test",
        personal_ai_context_service_account="pas@health.test",
        personal_ai_context_read_enabled=True,
        personal_ai_r5_preview_enabled=True,
        personal_ai_health_dispatch_test_enabled=True,
    )
    uid = "synthetic-dispatch-user"
    owner = seed_owner(db_session, uid)
    selection = seed_profile(db_session, owner)
    db_session.commit()
    sessions = sessionmaker(bind=postgres_engine, expire_on_commit=False)
    authority = make_authority(selection, subject=uid)
    source_request = wire(selection)
    dest = {
        "account": "fixture",
        "connection": "c1",
        "endpoint": "loopback-fixture",
        "model": "fake",
        "provider": "fake",
        "revision": 1,
        "runtime": "r1",
    }
    destination_digest = digest(canonical_json(dest))
    target = R5VerifiedCallerTarget(
        "usr_" + "a" * 32,
        "health-fixture",
        uuid4(),
        digest(b"original PAS target fingerprint"),
        "fixture-actor-handle",
        "source-1",
        "policy-1",
    )
    intent = uuid4()
    original = reserve_r5_operation_keys(
        sessions,
        settings,
        intent_id=intent,
        request=source_request,
        authority=authority,
        target=target,
        current_intent=lambda _: True,
        reauthorize=lambda: (authority, target),
    )
    old_key, pas, runtime = [Ed25519PrivateKey.generate() for _ in range(3)]
    conversation = uuid4()
    create_response = f'{{"conversation_id": "{conversation}"}}'.encode()
    now = int(datetime.now(UTC).timestamp())
    create_header = signed_header(
        _receipt_binding(
            owner,
            authority,
            target,
            original,
            conversation,
            digest(r5_create_request(original)),
            purpose="create",
        ),
        create_response,
        now,
        old_key,
    )
    preview_request = {
        "idempotency_key": str(original.preview),
        "choice": {"mode": "user_owned_plan"},
        "content": "Synthetic dispatch",
    }
    request_digest = digest(canonical_json(preview_request))
    if getattr(request, "param", None) != "unbound":
        assert bind_r5_preview_request(
            sessions,
            settings,
            intent_id=intent,
            source_request=source_request,
            authority=authority,
            target=target,
            reauthorize=lambda: (authority, target),
            original=original,
            current_intent=lambda _: True,
            create_response=create_response,
            create_receipt=create_header,
            receipt_keys={"old-r5": old_key.public_key()},
            request=preview_request,
        ) == (conversation, request_digest)
    epochs = R5PreviewEpochs(
        digest(b"active branch"),
        {
            "application": "health",
            "provider": "fake",
            "model": "fake",
            "runtime": "local:r1",
            "recipient": "openai-responses:fixture",
        },
        {"source": "grant-1"},
        {"memory": "grant-1"},
    )
    inventory = [
        {"category": "conversation_history", "turns": 1},
        {"category": "ai_memory", "fields": ["content"]},
        {"category": "domain_current", "fields": ["record"]},
    ]
    legacy_confirmation = digest(b"old R5 metadata confirmation")
    preview_response = json.dumps(
        {
            "confirmation": legacy_confirmation,
            "destination": dict(epochs.destination),
            "purpose": "foreground_application_plan",
            "selected_context": inventory,
            "input_tokens_estimated": 3,
            "expires_at": (datetime.fromtimestamp(now, UTC) + timedelta(seconds=30)).isoformat(),
        }
    ).encode()
    preview_header = signed_header(
        _receipt_binding(
            owner, authority, target, original, conversation, request_digest, purpose="preview"
        )
        | {
            "branch_digest": epochs.branch_digest,
            "actual_revision": selection.revision,
            "permission_version": f"health-object-v1:r{selection.revision}:ai1:cross1",
            "source_sensitivity": "restricted",
            "source_grants": dict(epochs.source_grants),
            "memory_grants": dict(epochs.memory_grants),
            "inventory_digest": digest(canonical_json(inventory)),
            "confirmation": legacy_confirmation,
            "destination": dict(epochs.destination),
        },
        preview_response,
        now,
        old_key,
    )
    human = Principal("fixture-human", "person-1")
    enrollment = Enrollment(
        authority.enrollment_id,
        authority.enrollment_generation,
        owner,
        Principal(authority.identity.issuer, authority.identity.subject),
        human,
        target.pas_owner_id,
        str(authority.installation_id),
        target.client_namespace,
        "fixture-tenant",
        "fixture-health",
    )
    memory = digest(b"independently prepared PAS memory")
    live = LiveAuthority(
        Principal("https://accounts.google.com", settings.personal_ai_context_service_account),
        settings.personal_ai_context_service_audience,
        True,
        True,
        human,
        target,
        authority,
        (enrollment,),
        epochs,
        1,
        0,
        True,
        True,
        "restricted",
        memory,
        destination_digest,
        1,
    )
    _, projection = read_r5_health_preference(
        sessions, settings, source_request, authority, lambda: authority
    )
    binding = Binding(
        canonical_json(
            {
                "actor_issuer": human.issuer,
                "app": "health",
                "attempt": str(uuid4()),
                "branch": epochs.branch_digest,
                "client": target.client_namespace,
                "conversation": str(conversation),
                "create_key": str(original.create),
                "create_receipt": receipt_digest(create_header),
                "destination": dest,
                "epoch": 1,
                "installation": enrollment.installation,
                "memory": memory,
                "original_key": str(original.preview),
                "owner": target.pas_owner_id,
                "policy": target.policy_epoch,
                "preview_receipt": receipt_digest(preview_header),
                "root": str(uuid4()),
                "source": source_commitment(PROJECTION_KEY, projection, enrollment, 1, 0),
                "subject": human.subject,
                "target": enrollment.target,
                "tenant": enrollment.tenant,
                "workspace": None,
            }
        )
    )
    claims = {
        "audience": "health",
        "binding_sha256": binding.sha256,
        "expires": now + 60,
        "issuer": "pas",
        "kid": "p1",
        "payload_sha256": digest(b"synthetic only"),
        "purpose": "preview",
        "v": VERSION,
    }
    scope = PrivatePreview(
        intent, source_request, authority, target, original, conversation, request_digest, binding
    )
    return Case(
        settings,
        sessions,
        scope,
        live,
        owner,
        now,
        TestWitness(),
        RecordingTransport(sessions, scope),
        {
            "create_response": create_response,
            "create_header": create_header,
            "preview_response": preview_response,
            "preview_header": preview_header,
            "dispatch_envelope": canonical_json(
                {
                    "claims": claims,
                    "signature": encoded(pas.sign(canonical_json(claims))),
                }
            ),
        },
        old_key,
        pas,
        runtime,
    )


def test_native_concurrent_confirmation_durable_and_get_only(case: Case) -> None:
    caller = case.caller()
    reviewed = caller.prepare(case.scope, **case.artifacts)
    body = reviewed.preview.confirmation_body
    with pytest.raises(DispatchConflict):
        caller.confirm(reviewed, body + b" ")
    case.transport.post_failure = TimeoutError()
    barrier = Barrier(2)

    def confirm() -> None:
        barrier.wait()
        caller.confirm(reviewed, body)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(confirm) for _ in range(2)]
        for future in futures:
            future.result()
    path = f"/private/application-plan/v1/conversations/{case.scope.conversation}/continue"
    assert case.transport.posts == [(path, MEDIA_TYPE, body)]
    assert caller.observe(case.scope) is None
    assert case.caller().observe(case.scope) is None
    caller.confirm(reviewed, body)
    assert len(case.transport.posts) == 1
    assert len(case.transport.gets) == 2
    assert all(headers["X-Application-ID"] == "health" for _, headers in case.transport.gets)

    with case.sessions() as session:
        evidence = json.loads(export_owner_snapshot(session, case.owner))["data"][
            "health_dispatch_intents"
        ]
        assert len(evidence) == 1
        assert evidence[0]["create_receipt_digest"] == receipt_digest(
            case.artifacts["create_header"]
        )
        assert evidence[0]["preview_receipt_digest"] == receipt_digest(
            case.artifacts["preview_header"]
        )
        assert not any(
            value in str(evidence)
            for value in (
                "bullets",
                "synthetic-dispatch-user",
                '"preview_sig":',
                case.artifacts["preview_header"],
            )
        )
    with (
        pytest.raises(DBAPIError, match="invalid or immutable"),
        case.sessions() as session,
        session.begin(),
    ):
        session.execute(update(HealthDispatchIntent).values(body_digest="a" * 64))


def test_identity_recipient_replay_source_and_original_artifacts(case: Case) -> None:
    caller = case.caller()
    good = case.live
    assert good
    for invalid in (
        replace(good, service_audience="https://shopping.test"),
        replace(good, pas_human=Principal(good.pas_human.issuer, "same-email-different-subject")),
        replace(good, firebase_revocation_checked=False),
        replace(good, foreground=False),
        replace(good, enrollments=good.enrollments * 2),
        replace(good, enrollments=(replace(good.enrollments[0], active=False),)),
        replace(good, recipient_memory_grant=False),
        replace(good, recipient_source_grant=False),
        replace(good, source_sensitivity_ceiling="ordinary"),
        replace(good, memory_commitment=digest(b"other memory")),
        replace(good, consent_epoch=2),
        replace(good, erasure_epoch=1),
    ):
        case.live = invalid
        with pytest.raises(DispatchUnavailable):
            caller.prepare(case.scope, **case.artifacts)
    case.live = good
    nonce = uuid4()
    assert caller.current(case.scope, "preview", nonce)["current"] is True
    another_nonce = UUID("00000000-0000-7000-8000-000000000001")
    assert caller.current(case.scope, "preview", another_nonce)["current"] is True
    assert caller.current(case.scope, "release", uuid4())["current"] is False
    with pytest.raises(DispatchUnavailable):
        caller.current(case.scope, "preview", nonce)
    for name in ("create_header", "preview_header", "create_response", "preview_response"):
        changed = case.artifacts[name]
        altered = changed + (b" " if isinstance(changed, bytes) else " ")
        with pytest.raises(DispatchUnavailable):
            caller.prepare(case.scope, **(case.artifacts | {name: altered}))
    assert caller.observe(case.scope) is None
    with case.sessions() as session:
        assert session.get(HealthDispatchIntent, case.scope.original.preview) is None
    reviewed = caller.prepare(case.scope, **case.artifacts)
    with case.sessions() as session:
        update_profile_item(
            session,
            case.owner,
            case.scope.authority.selection.object_id,
            1,
            {"cross_domain_use_allowed": False},
        )
        session.commit()
    with pytest.raises(DispatchUnavailable):
        caller.confirm(reviewed, reviewed.preview.confirmation_body)
    assert not case.transport.posts and not case.transport.gets


def test_interruption_before_native_commit_consumes_fixture_checkpoint(
    case: Case,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    caller = case.caller()
    reviewed = caller.prepare(case.scope, **case.artifacts)

    def interrupted(*args: Any) -> bool:
        raise DispatchUnavailable

    monkeypatch.setattr(caller, "_record", interrupted)
    with pytest.raises(DispatchUnavailable):
        caller.confirm(reviewed, reviewed.preview.confirmation_body)
    restarted = case.caller()
    recovered = restarted.prepare(case.scope, **case.artifacts)
    restarted.confirm(recovered, recovered.preview.confirmation_body)
    assert restarted.observe(case.scope) is None
    assert not case.transport.posts and not case.transport.gets


def test_post_commit_authority_loss_cannot_be_resumed(
    case: Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    caller = case.caller()
    reviewed = caller.prepare(case.scope, **case.artifacts)
    body = reviewed.preview.confirmation_body
    good = case.live
    original = caller._record

    def record(*args: Any) -> bool:
        answer = original(*args)
        case.live = None
        return answer

    monkeypatch.setattr(caller, "_record", record)
    with pytest.raises(DispatchUnavailable):
        caller.confirm(reviewed, body)
    case.live = good
    caller.confirm(reviewed, body)
    assert case.caller().observe(case.scope) is None
    assert not case.transport.posts
    case.witness.generation = 2
    with pytest.raises(DispatchUnavailable):
        caller.observe(case.scope)


def test_expiration_and_erasure_suppress_read_and_keep_checkpoint(
    case: Case, tmp_path: Path
) -> None:
    caller = case.caller()
    reviewed = caller.prepare(case.scope, **case.artifacts)
    initial = case.now
    case.now = reviewed.deadline
    with pytest.raises(DispatchExpired):
        caller.confirm(reviewed, reviewed.preview.confirmation_body)
    case.now = initial
    reviewed = caller.prepare(case.scope, **case.artifacts)
    caller.confirm(reviewed, reviewed.preview.confirmation_body)
    with case.sessions() as session:
        deletion = begin_owner_deletion(session, case.owner, uuid4())
        with pytest.raises(DispatchUnavailable):
            caller.observe(case.scope)
        completed = process_owner_deletion(
            session, case.owner, deletion.id, LocalObjectStorage(tmp_path, max_size_bytes=1024)
        )
        assert completed.status == "completed"
    with case.sessions() as session:
        assert session.get(HealthDispatchIntent, case.scope.original.preview) is None
    assert case.scope.original.preview in case.witness.records
    assert not case.transport.gets


@pytest.mark.parametrize(
    "outcome", ["valid", "wrong-root", "wrong-result", "expired", "expires-at-detail"]
)
def test_terminal_scope_bytes_and_reauthorization(case: Case, outcome: str) -> None:
    caller = case.caller()
    reviewed = caller.prepare(case.scope, **case.artifacts)
    body = reviewed.preview.confirmation_body
    caller.confirm(reviewed, body)
    fields = case.scope.binding.fields
    message = str(uuid4())
    result = "Synthetic response"
    terminal = {
        "attempt": fields["attempt"],
        "audience": "pas",
        "binding_sha256": case.scope.binding.sha256,
        "body_sha256": digest(body),
        "expires": case.now + 30,
        "issuer": "runtime",
        "kid": "r1",
        "message_id": message,
        "purpose": "terminal",
        "result_sha256": digest(result.encode()),
        "root": fields["root"],
        "v": VERSION,
    }
    status = {name: fields[name] for name in ("attempt", "original_key", "root")} | {
        "body_sha256": digest(body),
        "message_id": message,
        "state": "completed",
    }
    detail = {name: fields[name] for name in ("attempt", "original_key", "root")} | {
        "message_id": message,
        "result": result,
    }

    response_headers = (
        ("Content-Type", MEDIA_TYPE),
        ("Cache-Control", "no-store"),
        ("x-pas-committed-at", str(case.now - 1)),
    )

    def status_response(claims: dict[str, Any]) -> FixtureResponse:
        return FixtureResponse(
            200,
            canonical_json(
                status
                | {
                    "terminal": claims,
                    "signature": encoded(case.runtime.sign(canonical_json(claims))),
                }
            ),
            response_headers,
        )

    if outcome == "wrong-root":
        altered = terminal | {"root": str(uuid4())}
    elif outcome == "expired":
        altered = terminal | {"expires": case.now}
    else:
        altered = terminal
    if outcome == "wrong-result":
        detail["result"] = "wrong"
    if outcome == "expires-at-detail":
        case.transport.after_detail = lambda: setattr(case, "now", terminal["expires"])
    case.transport.replies = [
        status_response(altered),
        FixtureResponse(200, canonical_json(detail), response_headers),
    ]
    if outcome == "valid":
        assert caller.observe(case.scope) == result
        good = case.live
        case.transport.replies = [status_response(terminal)]
        case.transport.after_status = lambda: setattr(case, "live", None)
        assert caller.observe(case.scope) is None
        case.live = good
        case.key_active = False
        with pytest.raises(DispatchUnavailable):
            caller.observe(case.scope)
    else:
        assert caller.observe(case.scope) is None
        assert len(case.transport.gets) == (1 if outcome in ("wrong-root", "expired") else 2)
        with case.sessions() as session:
            row = session.get(HealthDispatchIntent, case.scope.original.preview)
            assert row is not None and row.quarantined_at is not None
        case.transport.replies = [
            status_response(terminal),
            FixtureResponse(200, canonical_json(detail | {"result": result}), response_headers),
        ]
        with pytest.raises(DispatchUnavailable):
            case.caller().observe(case.scope)
    assert len(case.transport.posts) == 1


@pytest.mark.parametrize("case", ["unbound"], indirect=True)
def test_acquire_private_preview_with_original_proof_and_pending_callback(case: Case) -> None:
    caller = case.caller()
    pending = replace(
        case.scope,
        binding=Binding(canonical_json(case.scope.binding.fields | {"preview_receipt": "0" * 64})),
    )
    callback = caller.registered_source(
        lambda conversation, original: (
            pending
            if (conversation, original) == (pending.conversation, pending.original.preview)
            else None
        )
    )

    def reply() -> FixtureResponse:
        path, media, body = case.transport.posts[0]
        assert (
            path
            == f"/private/application-plan/v1/conversations/{pending.conversation}/context-preview"
        )
        assert media == MEDIA_TYPE
        assert body == canonical_json(
            {
                "content": "Synthetic dispatch",
                "idempotency_key": str(pending.original.preview),
                "choice": {"mode": "user_owned_plan"},
            }
        )
        nonce = str(uuid4())
        assert callback(case.scope.binding.raw, "preview", nonce) == {
            "binding_sha256": case.scope.binding.sha256,
            "phase": "preview",
            "nonce": nonce,
            "current": True,
            "expires": case.now + 1,
        }
        with pytest.raises(DispatchUnavailable):
            callback(case.scope.binding.raw, "preview", nonce)
        with pytest.raises(DispatchUnavailable):
            callback(
                canonical_json(case.scope.binding.fields | {"root": str(uuid4())}),
                "preview",
                str(uuid4()),
            )
        return FixtureResponse(
            200,
            case.artifacts["preview_response"],
            (
                ("content-type", MEDIA_TYPE),
                ("cache-control", "no-store"),
                ("x-application-plan-receipt", case.artifacts["preview_header"]),
                (PREVIEW_HEADER, case.artifacts["dispatch_envelope"].decode("ascii")),
            ),
        )

    case.transport.preview = reply
    kwargs = {
        "content": "Synthetic dispatch",
        "create_response": case.artifacts["create_response"],
        "create_header": case.artifacts["create_header"],
    }
    reviewed = caller.acquire_preview(pending, **kwargs)
    assert reviewed.scope == case.scope
    assert reviewed.original_preview.digest == receipt_digest(case.artifacts["preview_header"])
    with pytest.raises(DispatchUnavailable):
        caller.acquire_preview(pending, **kwargs)
    # A restarted callback can independently resolve the exact submitted binding.
    caller.confirm(reviewed, reviewed.preview.confirmation_body)
    recovered = case.caller().registered_source(
        lambda conversation, original: (
            case.scope
            if (conversation, original) == (case.scope.conversation, case.scope.original.preview)
            else None
        )
    )
    assert recovered(case.scope.binding.raw, "send", str(uuid4()))["current"] is True
    assert len(case.transport.posts) == 2
