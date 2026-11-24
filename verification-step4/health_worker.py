"""Drive the reviewed Health caller against a dedicated PAS and receiving process."""

import argparse
import json
import os
import select as selector
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from secrets import token_bytes
from threading import Barrier, Lock
from types import SimpleNamespace
from uuid import UUID, uuid4, uuid5

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common import (
    CONTENT,
    FIREBASE_ISSUER,
    HEALTH_AUDIENCE,
    PAS_AUDIENCE,
    PREFERENCE,
    RESULT,
)
from common import (
    SERVICE,
    TENANT,
    QuietHandler,
    canonical,
    digest,
    listener,
    network_fence,
    request,
)
from health_loopback_proof import PROOF_HEADER, TRANSACTION_HEADER, sign, verify
from health_api.application.health_dispatch import (
    ContinuityRecord,
    DispatchUnavailable,
    Enrollment,
    FixtureResponse,
    HealthDispatchCaller,
    LiveAuthority,
    Principal,
    PrivatePreview,
    source_commitment,
)
from health_api.application.personal_ai_context import read_personal_ai_health_context
from health_api.application.profile_service import (
    CreateProfile,
    create_profile_item,
    update_profile_item,
)
from health_api.application.r5_health_caller import (
    R5PreviewEpochs,
    R5VerifiedCallerTarget,
    r5_create_request,
    reserve_r5_operation_keys,
)
from health_api.application.r5_health_source import (
    R5HealthSelection,
    R5SourceAuthority,
    read_r5_health_preference,
    resolve_r5_owner,
)
from health_api.config.settings import Settings
from health_api.domain.schemas import ProfilePayloadV1, ProfileValidity
from health_api.integrations.firebase_auth import (
    FirebaseTokenVerifier,
    TokenVerificationError,
)
from health_api.integrations.pas_dispatch import Binding, MEDIA_TYPE, PinnedKey
from health_api.integrations.personal_ai_context import HealthContextReadRequest
from health_api.integrations.personal_ai_context_auth import (
    PersonalAIContextIdentityVerifier,
)
from health_api.integrations.personal_ai_preview_receipt import PROFILE_PATH
from health_api.persistence.models import HealthDispatchIntent, ProviderIdentity, User

HERE = Path(__file__).resolve().parent
HEALTH = HERE.parent
PAS = HEALTH.parent / "pas"


@contextmanager
def process(python, target, config, *, env, cwd):
    child = subprocess.Popen(
        [python, "-sB", str(HERE / target)],
        env=env,
        cwd=cwd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    def receive():
        assert selector.select([child.stdout], [], [], 30)[0], (
            f"{target} control timeout"
        )
        line = child.stdout.readline()
        assert line, f"{target} exited {child.poll()}"
        return json.loads(line)

    def command(operation, **values):
        child.stdin.write(json.dumps([operation, values]) + "\n")
        child.stdin.flush()
        return receive()

    try:
        child.stdin.write(json.dumps(config) + "\n")
        child.stdin.flush()
        yield receive(), command
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=5)
        child.stdin.close()
        child.stdout.close()


class Checkpoint:
    def __init__(self, path):
        self.path = path
        with sqlite3.connect(path) as db:
            db.execute(
                "CREATE TABLE records (original TEXT PRIMARY KEY, evidence TEXT)"
            )
        os.chmod(path, 0o600)

    def current(self, generation, record):
        if generation != 1:
            return False
        if record is None:
            return self.path.is_file()
        with sqlite3.connect(self.path) as db:
            return db.execute(
                "SELECT evidence FROM records WHERE original=?",
                (str(record.original_key),),
            ).fetchone() == (self.encode(record),)

    @staticmethod
    def encode(record: ContinuityRecord):
        return json.dumps(asdict(record), default=str, sort_keys=True)

    def reserve(self, record):
        with sqlite3.connect(self.path) as db:
            db.execute("PRAGMA synchronous=FULL")
            return (
                db.execute(
                    "INSERT OR IGNORE INTO records VALUES (?,?)",
                    (str(record.original_key), self.encode(record)),
                ).rowcount
                == 1
            )


def public(encoded):
    return Ed25519PublicKey.from_public_bytes(bytes.fromhex(encoded))


def denial(call):
    try:
        return call()
    except DispatchUnavailable:
        return None


class HealthLane:
    def __init__(
        self, scenario, directory, stack, sessions, receiver, proof_key, network_ports
    ):
        self.scenario = scenario
        self.events = []
        self.callbacks = []
        self.callbacks_lock = Lock()
        self.sessions = sessions
        self.receiver = receiver
        self.proof_key = proof_key
        self.projection_key = token_bytes(32)
        self.case_state = {}
        self.settings = Settings(
            _env_file=None,
            app_env="test",
            auth_mode="firebase",
            firebase_project_id="health-fixture",
            personal_ai_context_service_audience=HEALTH_AUDIENCE,
            personal_ai_context_service_account=SERVICE,
            personal_ai_context_read_enabled=True,
            personal_ai_r5_preview_enabled=True,
            personal_ai_health_dispatch_test_enabled=True,
        )
        self.start = int(datetime.now(UTC).timestamp())
        self.uid = f"synthetic-firebase-{uuid4()}"
        self.token = uuid4().hex
        self.uid_live = self.uid
        self.firebase_revoked = False
        self.subject = f"paired-health-{uuid4()}"
        self.checkpoint = Checkpoint(directory / "health-witness.sqlite")
        with sessions() as session, session.begin():
            user = User(id=uuid4(), display_timezone="UTC")
            other = User(id=uuid4(), display_timezone="UTC")
            session.add_all([user, other])
            session.flush()
            for owner, uid in ((user.id, self.uid), (other.id, self.uid + "-other")):
                session.add(
                    ProviderIdentity(issuer=FIREBASE_ISSUER, subject=uid, user_id=owner)
                )
            self.owner = user.id
            self.other_owner = other.id
            self.records = [
                create_profile_item(
                    session,
                    self.owner,
                    CreateProfile(
                        id=uuid4(),
                        profile=ProfilePayloadV1.model_validate(PREFERENCE),
                        validity=ProfileValidity(),
                        ai_use_allowed=True,
                        cross_domain_use_allowed=True,
                    ),
                ).aggregate[0]
                for _ in range(2)
            ]
        self.firebase = FirebaseTokenVerifier(
            "health-fixture", timeout_seconds=1, max_in_flight=8
        )
        firebase = self.firebase

        def firebase_claims(token, *, app, check_revoked):
            if (
                token != self.token
                or self.firebase_revoked
                or check_revoked is not True
            ):
                raise TokenVerificationError
            return {
                "iss": FIREBASE_ISSUER,
                "aud": "health-fixture",
                "sub": self.uid_live,
                "auth_time": self.start,
                "iat": self.start,
            }

        class FirebaseError(Exception):
            pass

        firebase._sdk = lambda: (
            SimpleNamespace(
                get_app=lambda _: None,
                exceptions=SimpleNamespace(FirebaseError=FirebaseError),
            ),
            SimpleNamespace(
                verify_id_token=firebase_claims,
                InvalidIdTokenError=TokenVerificationError,
                ExpiredIdTokenError=TokenVerificationError,
                RevokedIdTokenError=TokenVerificationError,
                UserDisabledError=TokenVerificationError,
                UserNotFoundError=TokenVerificationError,
                CertificateFetchError=FirebaseError,
            ),
        )
        self.authority = R5SourceAuthority(
            firebase.verify(self.token),
            uuid4(),
            1,
            uuid4(),
            R5HealthSelection(self.records[0].id, self.records[0].revision),
        )
        self.seen = set()
        self.send_checks = 0
        lane = self

        class Callback(QuietHandler):
            def do_POST(self):
                try:
                    raw = self.read()
                    proof = self.headers.get(PROOF_HEADER)
                    nonce = verify(
                        lane.proof_key, HEALTH_AUDIENCE, "POST", self.path, raw, proof
                    )
                    with lane.callbacks_lock:
                        if not nonce or nonce in lane.seen:
                            raise ValueError("invalid or replayed callback")
                        lane.seen.add(nonce)
                    verifier = PersonalAIContextIdentityVerifier()
                    verifier._google_claims = lambda token, audience: (
                        {"email": SERVICE, "email_verified": True}
                        if token == proof and audience == HEALTH_AUDIENCE
                        else {}
                    )
                    verifier.verify(
                        service_token=proof,
                        user_token=lane.token,
                        settings=lane.settings,
                        user_verifier=lane.firebase,
                    )
                    if self.path == "/health/context":
                        answer = lane.source(raw)
                    elif self.path == "/health/current":
                        body = json.loads(raw)
                        if body["phase"] == "send":
                            lane.send_checks += 1
                            if (
                                lane.scenario == "health-revoked-after-fence"
                                and lane.send_checks == 2
                            ):
                                lane.fix_consent("cross_domain_use_allowed", False, 1)
                        current = lane.resolve(
                            body["binding"].encode(), body["phase"], body["nonce"]
                        )
                        answer = canonical(current)
                        with lane.callbacks_lock:
                            lane.callbacks.append((body["phase"], current["current"]))
                    else:
                        raise ValueError("unexpected callback route")
                    self.respond(200, answer, content_type="application/json")
                except (ValueError, TokenVerificationError):
                    self.respond(403)

        self.callback = listener(Callback)
        stack.callback(self.callback.server_close)
        stack.callback(self.callback.shutdown)
        pas_dir = directory / "pas"
        pas_dir.mkdir(mode=0o700)
        self.info, self.control = stack.enter_context(
            process(
                os.environ["PAS_PYTHON"],
                "pas_worker.py",
                {
                    "directory": str(pas_dir),
                    "health_port": self.callback.server_port,
                    "receiver_port": receiver["port"],
                    "receiver_key": receiver["key"],
                    "proof_key": proof_key.hex(),
                    "projection_key": self.projection_key.hex(),
                    "memory_key": token_bytes(32).hex(),
                    "subject": self.subject,
                    "fault": scenario,
                    "health_binding": {
                        "owner": str(self.owner),
                        "enrollment_id": str(self.authority.enrollment_id),
                        "installation_id": str(self.authority.installation_id),
                        "object_id": str(self.records[0].id),
                        "revision": self.records[0].revision,
                    },
                },
                env={
                    "PATH": os.environ["PATH"],
                    "PAS_PAIRED_DSN": os.environ["PAS_PAIRED_DSN"],
                    "PYTHONPATH": os.pathsep.join(
                        (
                            str(PAS / "backend"),
                            str(PAS / "backend/src"),
                            str(PAS / "reference-apps/src"),
                            str(PAS / "sdk/python/src"),
                        )
                    ),
                    "LITELLM_LOCAL_MODEL_COST_MAP": "True",
                },
                cwd=PAS / "backend",
            )
        )
        network_ports.add(self.info["port"])
        self.branch_id = uuid4()
        self.target = R5VerifiedCallerTarget(
            self.info["owner"],
            self.info["client"],
            self.branch_id,
            self.info["recipient_digest"],
            self.info["actor"],
            self.info["source_epoch"],
            self.info["policy"],
        )
        self.enrollment = Enrollment(
            self.authority.enrollment_id,
            1,
            self.owner,
            Principal(FIREBASE_ISSUER, self.uid),
            Principal(self.info["issuer"], self.info["subject"]),
            self.info["owner"],
            str(self.authority.installation_id),
            self.info["client"],
            TENANT,
            self.info["target"],
        )
        self.source_request = canonical(self.info["selection"])
        self.intent = uuid4()
        self.original = reserve_r5_operation_keys(
            sessions,
            self.settings,
            intent_id=self.intent,
            request=self.source_request,
            authority=self.authority,
            target=self.target,
            current_intent=lambda _: True,
            reauthorize=lambda: (self.current_source(), self.target),
        )
        create_body = r5_create_request(self.original)
        nonce_headers = self.control("create-proof", body=json.loads(create_body))[
            "headers"
        ]
        create = self.send("POST", PROFILE_PATH, create_body, nonce_headers)
        assert create.status == 201
        self.cid = UUID(json.loads(create.raw)["conversation_id"])
        self.create = create
        self.approved = self.control(
            "setup-preview",
            conversation=str(self.cid),
            original=str(self.original.preview),
            create=str(self.original.create),
            create_response=create.raw.decode(),
            create_header=create.header("x-application-plan-receipt"),
            branch_id=str(self.branch_id),
        )
        self.caller = self.new_caller()
        self.resolve = self.caller.registered_source(self.lookup)
        scope_key = digest(
            canonical(
                [
                    TENANT,
                    None,
                    "health",
                    self.info["owner"],
                    self.info["client"],
                    str(self.cid),
                    str(self.original.preview),
                ]
            )
        )
        self.root = uuid5(self.cid, "pas-dispatch/1:" + scope_key)
        self.attempt = uuid5(self.root, "foreground")
        _, projection = read_r5_health_preference(
            sessions,
            self.settings,
            self.source_request,
            self.authority,
            self.current_source,
        )
        dest = self.info["destination"]
        self.epochs = R5PreviewEpochs(
            self.approved["branch"],
            {
                "application": "health",
                "model": dest["model"],
                "provider": dest["provider"],
                "runtime": "local:" + dest["runtime"],
                "recipient": "openai-responses:" + dest["account"],
            },
            self.approved["source_grants"],
            self.approved["memory_grants"],
        )
        body = {
            "idempotency_key": str(self.original.preview),
            "choice": {"mode": "user_owned_plan"},
            "content": CONTENT,
        }
        self.scope = PrivatePreview(
            self.intent,
            self.source_request,
            self.authority,
            self.target,
            self.original,
            self.cid,
            digest(canonical(body)),
            Binding(
                canonical(
                    {
                        "actor_issuer": self.enrollment.pas_human.issuer,
                        "app": "health",
                        "attempt": str(self.attempt),
                        "branch": self.epochs.branch_digest,
                        "client": self.target.client_namespace,
                        "conversation": str(self.cid),
                        "create_key": str(self.original.create),
                        "create_receipt": digest(
                            create.header("x-application-plan-receipt").encode()
                        ),
                        "destination": dest,
                        "epoch": 1,
                        "installation": self.enrollment.installation,
                        "memory": self.approved["memory_commitment"],
                        "original_key": str(self.original.preview),
                        "owner": self.target.pas_owner_id,
                        "policy": self.target.policy_epoch,
                        "preview_receipt": "0" * 64,
                        "root": str(self.root),
                        "source": source_commitment(
                            self.projection_key, projection, self.enrollment, 1, 0
                        ),
                        "subject": self.enrollment.pas_human.subject,
                        "target": self.enrollment.target,
                        "tenant": TENANT,
                        "workspace": None,
                    }
                )
            ),
        )

    def current_source(self):
        identity = self.firebase.verify(self.token)
        return replace(
            self.authority,
            identity=identity,
            selection=self.case_state.get("selection", self.authority.selection),
        )

    def source(self, raw):
        inquiry = HealthContextReadRequest.model_validate_json(raw)
        active = self.current_source()
        if inquiry.operation == "profile":
            _, response = read_r5_health_preference(
                self.sessions,
                self.settings,
                raw,
                self.authority,
                self.current_source,
            )
        elif (
            inquiry.operation == "verify"
            and inquiry.category == "profile_preferences"
            and inquiry.entity_refs[0].object_id == active.selection.object_id
            and inquiry.fields == ("permission_version",)
        ):
            with self.sessions() as session, session.begin():
                owner = resolve_r5_owner(session, active)
                response = read_personal_ai_health_context(session, owner, inquiry)
        else:
            raise ValueError("misbound selected context")
        return canonical(response.model_dump(mode="json"))

    def authority_now(self):
        try:
            authority = self.current_source()
        except TokenVerificationError:
            return None
        return LiveAuthority(
            Principal("https://accounts.google.com", SERVICE),
            self.case_state.get("service_audience", HEALTH_AUDIENCE),
            True,
            True,
            self.enrollment.pas_human,
            self.target,
            authority,
            (
                replace(
                    self.enrollment,
                    health_owner=self.case_state.get("owner", self.owner),
                ),
            ),
            self.epochs,
            self.case_state.get("epoch", 1),
            0,
            not self.case_state.get("health_recipient"),
            True,
            "restricted",
            self.approved["memory_commitment"],
            self.case_state.get(
                "recipient_digest", digest(canonical(self.info["destination"]))
            ),
            1,
        )

    def lookup(self, conversation, original):
        if (conversation, original) == (self.cid, self.original.preview):
            return self.scope
        return None

    def new_caller(self):
        info = self.info
        return HealthDispatchCaller(
            self.sessions,
            self.settings,
            current_authority=self.authority_now,
            current_intent=lambda keys: keys == self.original,
            original_keys={info["original_kid"]: public(info["old_key"])},
            preview_key=PinnedKey(
                "pas-health-paired",
                "preview",
                "health",
                "preview",
                public(info["preview_key"]),
                lambda: True,
            ),
            terminal_key=PinnedKey(
                "runtime-health-paired",
                "terminal",
                "pas-health-paired",
                "terminal",
                public(info["terminal_key"]),
                lambda: not self.case_state.get("terminal_inactive"),
            ),
            projection_key=self.projection_key,
            witness=self.checkpoint,
            transport=self,
            now=lambda: info["now"] + self.case_state.get("clock_offset", 0),
        )

    def send(self, method, path, body=None, headers=None):
        hdrs = {"x-application-id": "health", "authorization": self.info["auth"]} | {
            name.lower(): value for name, value in (headers or {}).items()
        }
        if method == "POST" and TRANSACTION_HEADER in hdrs:
            hdrs[PROOF_HEADER] = sign(
                self.proof_key,
                PAS_AUDIENCE,
                method,
                path,
                body,
                nonce=hdrs[TRANSACTION_HEADER],
            )
        return FixtureResponse(*request(self.info["port"], method, path, body, hdrs))

    def post(self, path, headers, body):
        event = {
            "method": "POST",
            "route": path.rsplit("/", 1)[-1],
            "digest": digest(body),
        }
        self.events.append(event)
        if path.endswith("/context-preview"):
            nonce = self.approved["headers"][TRANSACTION_HEADER]
            headers = dict(headers) | {TRANSACTION_HEADER: nonce}
        if path.endswith("/continue"):
            with self.sessions() as session:
                row = session.get(HealthDispatchIntent, self.original.preview)
                assert row is not None and row.body_digest == digest(body)
                event["health_journal_committed"] = True
        response = self.send("POST", path, body, dict(headers))
        event["status"] = response.status
        if path.endswith("/context-preview") and response.status == 200:
            self.case_state["legacy_confirmation"] = json.loads(response.raw)[
                "confirmation"
            ]
        event["returned_bytes"] = len(response.raw)
        if self.scenario == "lost-ack" and path.endswith("/continue"):
            raise TimeoutError("drop the acknowledged continuation response")
        return response

    def get(self, path, headers):
        response = self.send("GET", path, headers=dict(headers))
        detail = "/continuations/" not in path
        if response.status == 200:
            expected = json.loads(response.raw)
            assert expected["original_key"] == str(self.original.preview)
            assert expected["root"] == str(self.root) and expected["attempt"] == str(
                self.attempt
            )
            if (
                not detail
                and self.scenario == "forged-terminal"
                and expected["state"] == "completed"
            ):
                terminal = expected["terminal"] | {"root": str(uuid4())}
                response = replace(
                    response, raw=canonical(expected | {"terminal": terminal})
                )
            if detail and self.scenario == "changed-detail":
                response = replace(
                    response,
                    raw=canonical(expected | {"result": "Conflicting fixture data"}),
                )
            if not detail and expected["state"] == "completed":
                self.case_state["last_status"] = expected
            if detail and self.scenario == "expired-before-publication":
                self.case_state["clock_offset"] = (
                    self.case_state["last_status"]["terminal"]["expires"]
                    - self.info["now"]
                )
        self.events.append(
            {
                "method": "GET",
                "route": "detail" if detail else "status",
                "status": response.status,
                "returned_bytes": len(response.raw),
                "state": expected.get("state") if response.status == 200 else None,
            }
        )
        return response

    def fix_consent(self, field, value, revision):
        with self.sessions() as session, session.begin():
            update_profile_item(
                session,
                self.owner,
                self.authority.selection.object_id,
                revision,
                {field: value},
            )

    def run(self):
        reviewed = self.caller.acquire_preview(
            self.scope,
            content=CONTENT,
            create_response=self.create.raw,
            create_header=self.create.header("x-application-plan-receipt"),
        )
        self.scope = reviewed.scope
        body = reviewed.preview.confirmation_body
        path = f"{PROFILE_PATH}/{self.cid}/continue"
        status_path = (
            f"/v1/conversations/{self.cid}/continuations/{self.original.preview}"
        )
        detail_path = f"/v1/conversations/{self.cid}"
        before = self.control("report")
        assert (
            before["state"] == "unknown"
            and not before["issued"]
            and not before["native_root"]
        )
        assert self.caller.observe(self.scope) is None
        ordinary = self.send(
            "POST",
            path,
            canonical(
                {
                    "content": CONTENT,
                    "idempotency_key": str(self.original.preview),
                    "choice": {
                        "mode": "user_owned_plan",
                        "confirmation": self.case_state["legacy_confirmation"],
                    },
                }
            ),
            {"content-type": "application/json"},
        )
        assert ordinary.status == 422
        if self.scenario == "health-ai-consent":
            self.fix_consent("ai_use_allowed", False, 1)
        elif self.scenario == "health-cross-domain-consent":
            self.fix_consent("cross_domain_use_allowed", False, 1)
        elif self.scenario == "regrant-higher-epoch":
            self.fix_consent("cross_domain_use_allowed", False, 1)
            self.fix_consent("cross_domain_use_allowed", True, 2)
            self.case_state["epoch"] = 2
        elif self.scenario == "health-owner":
            self.uid_live += "-other"
            self.case_state["owner"] = self.other_owner
        elif self.scenario == "health-firebase-revoked":
            self.firebase_revoked = True
        elif self.scenario == "health-record":
            self.case_state["selection"] = R5HealthSelection(
                self.records[1].id, self.records[1].revision
            )
        elif self.scenario == "health-recipient":
            self.case_state["health_recipient"] = True
        elif self.scenario == "health-crossed-recipient":
            self.case_state["recipient_digest"] = digest(
                b"different registered destination"
            )
        elif self.scenario == "crossed-pas-owner":
            response = self.send(
                "POST",
                path,
                body,
                {"content-type": MEDIA_TYPE, "authorization": self.info["wrong_auth"]},
            )
            assert response.status in {403, 404}, response.status
            if response.status == 403:
                assert json.loads(response.raw)["error"]["code"] == "access_denied"
            else:
                assert response.raw == b""
            self.case_state["crossed_pas_post_status"] = response.status
        elif self.scenario in {"pas-memory", "pas-source", "pas-owner", "pas-release"}:
            self.control("revoke", kind=self.scenario)
        elif self.scenario == "interrupt-after-health-commit":
            old_post = self.post

            def interrupted(*args):
                self.post = old_post
                raise TimeoutError("interruption before writing the HTTP confirmation")

            self.post = interrupted

        def confirm(caller):
            return caller.confirm(reviewed, body)

        health_denials = ("health-", "regrant-")
        if (
            self.scenario.startswith(health_denials)
            and self.scenario != "health-revoked-after-fence"
        ):
            try:
                confirm(self.caller)
            except DispatchUnavailable:
                pass
            else:
                raise AssertionError(
                    "current Health authority unexpectedly accepted a denied confirmation"
                )
        elif self.scenario == "concurrent":
            barrier = Barrier(2)

            def simultaneous():
                barrier.wait()
                confirm(self.caller)

            with ThreadPoolExecutor(max_workers=2) as pool:
                first, second = (pool.submit(simultaneous) for _ in range(2))
                first.result()
                second.result()
        elif self.scenario != "crossed-pas-owner":
            confirm(self.caller)

        replacement = self.new_caller()
        self.resolve = replacement.registered_source(self.lookup)
        outcome = None
        if self.scenario in {"ok", "concurrent", "lost-ack"}:
            outcome = replacement.observe(self.scope)
            assert outcome == RESULT
            status = self.case_state["last_status"]
            terminal = status["terminal"]
            assert terminal["binding_sha256"] == self.scope.binding.sha256
            assert terminal["body_sha256"] == status["body_sha256"] == digest(body)
            assert terminal["message_id"] == status["message_id"]
            assert terminal["result_sha256"] == digest(RESULT.encode())
            assert status["state"] == "completed"
            # Same original key and immutable confirmation bytes cannot trigger a resend.
            confirm(replacement)
            wrong_original = self.send(
                "GET",
                detail_path,
                headers={
                    "accept": MEDIA_TYPE,
                    "x-pas-original-key": str(uuid4()),
                },
            )
            assert wrong_original.status == 404 and not wrong_original.raw
            wrong_owner = self.send(
                "GET",
                status_path,
                headers={
                    "accept": MEDIA_TYPE,
                    "authorization": self.info["wrong_auth"],
                },
            )
            assert wrong_owner.status == 404 and not wrong_owner.raw
            self.case_state["health_recipient"] = True
            assert denial(lambda: replacement.observe(self.scope)) is None
            current_denied = self.send(
                "GET", status_path, headers={"accept": MEDIA_TYPE}
            )
            assert current_denied.status == 404 and not current_denied.raw
            self.case_state["health_recipient"] = False
            self.control("revoke", kind="pas-memory")
            assert replacement.observe(self.scope) is None
        elif self.scenario in {
            "429",
            "timeout",
            "disconnect",
            "pas-release",
            "interrupt-after-health-commit",
        }:
            assert replacement.observe(self.scope) is None
            confirm(replacement)
            assert replacement.observe(self.scope) is None
        elif self.scenario in {"pas-root-failure", "pas-after-fence"}:
            assert replacement.observe(self.scope) is None
            confirm(replacement)
            assert replacement.observe(self.scope) is None
        else:
            assert denial(lambda: replacement.observe(self.scope)) is None

        with self.sessions() as session:
            row = session.get(HealthDispatchIntent, self.original.preview)
            journal = (
                None
                if row is None
                else {
                    "binding_digest": row.binding_digest,
                    "body_digest": row.body_digest,
                    "quarantined": row.quarantined_at is not None,
                    "create_receipt_digest": row.create_receipt_digest,
                    "preview_receipt_digest": row.preview_receipt_digest,
                    "create_provenance": row.create_version,
                    "preview_provenance": row.preview_version,
                    "continuity_generation": row.continuity_generation,
                    "projection_and_payload_absent": not any(
                        field in row.__table__.columns.keys()
                        for field in (
                            "result",
                            "payload",
                            "projection",
                            "raw_receipt",
                            "messages",
                        )
                    ),
                }
            )
        if self.scenario in {
            "changed-detail",
            "expired-before-publication",
            "forged-terminal",
        }:
            assert journal["quarantined"] is True
            assert denial(lambda: replacement.observe(self.scope)) is None
        pas = self.control("report")
        assert not pas["network_denials"]
        phases = pas.pop("phases")
        assert len({nonce for _, nonce, _ in phases}) == len(phases)
        pas["callback_phases"] = [phase for phase, _, _ in phases]
        ack_events = [event for event in self.events if event["route"] == "continue"]
        return {
            "scenario": self.scenario,
            "health_pid": os.getpid(),
            "pas_pid": self.info["pid"],
            "receiver_pid": self.receiver["pid"],
            "health_port": self.callback.server_port,
            "pas_port": self.info["port"],
            "receiver_port": self.receiver["port"],
            "original_key": str(self.original.preview),
            "attempt": str(self.attempt),
            "branch": self.approved["branch"],
            "binding_digest": self.scope.binding.sha256,
            "source": {
                "object_id": str(self.records[0].id),
                "revision": self.records[0].revision,
                "field": "record",
                "sensitivity": "restricted",
                "initial_consent_epoch": 1,
                "initial_ai_use_allowed": True,
                "initial_cross_domain_use_allowed": True,
                "memory_id": self.approved["memory_id"],
            },
            "payload_digest": reviewed.preview.payload_digest,
            "health_confirmations": len(ack_events),
            "crossed_pas_post_status": self.case_state.get("crossed_pas_post_status"),
            "health_journal": journal,
            "health_wire": self.events,
            "health_reverse_checks": self.callbacks,
            "result_disclosed": outcome == RESULT,
            "ordinary_confirmation_status": ordinary.status,
            "pas": pas,
            "stores": self.info["stores"]
            | {
                "health_witness": str(self.checkpoint.path),
                "pas_native": self.info["native_backend"],
            },
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("scenarios", nargs="+")
    args = parser.parse_args()
    args.directory.mkdir(mode=0o700)
    engine = create_engine(os.environ["HEALTH_PAIRED_DSN"])
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    ports, denied_network = set(), []
    network_fence(ports, denied_network)
    for scenario in args.scenarios:
        directory = args.directory / scenario
        directory.mkdir(mode=0o700)
        observed = directory / "receiver.jsonl"
        with ExitStack() as stack:
            receiver, _ = stack.enter_context(
                process(
                    sys.executable,
                    "common.py",
                    {"observed": str(observed), "outcome": scenario},
                    env={"PATH": os.environ["PATH"]},
                    cwd=directory,
                )
            )
            lane = HealthLane(
                scenario, directory, stack, sessions, receiver, token_bytes(32), ports
            )
            result = lane.run()
            assert lane.control("stop") == {"stopped": True}
        received = (
            [json.loads(line) for line in observed.read_text().splitlines()]
            if observed.exists()
            else []
        )
        issued = result["pas"]["issued"]
        expected = (
            1
            if scenario
            in {
                "ok",
                "concurrent",
                "lost-ack",
                "429",
                "timeout",
                "disconnect",
                "changed-detail",
                "expired-before-publication",
                "forged-terminal",
            }
            else 0
        )
        assert len(issued) == len(received) == expected, (issued, received)
        assert not denied_network
        for sent, receipt in zip(issued, received, strict=True):
            assert sent["path"] == receipt["path"] == "/dispatch"
            assert (
                sent["digest"]
                == receipt["digest"]
                == receipt["declared_digest"]
                == result["payload_digest"]
            )
            assert sent["attempt"] == receipt["attempt"] == result["attempt"]
            assert receipt["has_health_preference"] and receipt["has_pas_memory"]
            assert receipt["model"] == "fake"
        assert result["health_confirmations"] <= 1
        expected_fences = (
            2
            if received or scenario in {"pas-after-fence", "health-revoked-after-fence"}
            else 0
        )
        assert result["pas"]["physical_fences"] == expected_fences, result["pas"]
        result["receiver"] = received
        print(json.dumps(result), flush=True)
    engine.dispose()


if __name__ == "__main__":
    main()
