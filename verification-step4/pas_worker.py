"""Standalone PAS fixture using the registered private ASGI routes and real loopback adapter."""

import hmac
import http.client
import json
import os
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path
from threading import Thread
from time import sleep
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
import uvicorn
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from common import CONTENT, HEALTH_AUDIENCE, PAS_AUDIENCE, TENANT
from common import canonical, digest, network_fence, output, request
from personal_ai.auth.scope import ApplicationScope, application_scope_context
from personal_ai.contracts.private_dispatch import Destination
from personal_ai.local_bridge.private_dispatch import LoopbackReceiver, RuntimeDispatch
from personal_ai.memory.dependencies import memory_dependency
from personal_ai.persistence.postgres import PostgresDatabase
from personal_ai.services.external_turns.dispatch_journal import (
    SyntheticDispatchJournal,
)
from personal_ai.services.external_turns.private_dispatch import (
    CreateBinding,
    CurrentSource,
    DispatchRegistration,
    PrivateDispatch,
)
from tests.conftest import offline_startup_mutation_inventory
from tests.app_context_support.health_loopback_proof import PROOF_HEADER, sign, verify
from tests.app_context_support.health_receipts import KEY_ID, decode
from tests.persistence.test_application_plan_postgres import (
    PlanWitness,
    native_attempts,
)
from tests.test_health_plan_preview import AUDIENCE, configure_preview, prepare, setup


def main(config):
    directory = Path(config["directory"])
    db = PostgresDatabase(os.environ["PAS_PAIRED_DSN"], environment="test", max_size=12)
    db.migrate()
    host_port = config["health_port"]
    receiver_port = config["receiver_port"]
    attempts = []
    network_fence({host_port, receiver_port}, attempts)
    key = bytes.fromhex(config["proof_key"])
    projection_key = bytes.fromhex(config["projection_key"])
    memory_key = bytes.fromhex(config["memory_key"])
    state = {
        "projection": None,
        "dependencies": {},
        "creates": {},
        "phases": [],
        "issued": [],
    }
    start = int(datetime.now(UTC).timestamp())
    clock = lambda: start

    def health(path, body):
        status, raw, headers = request(
            host_port,
            "POST",
            path,
            body,
            {
                PROOF_HEADER: sign(key, HEALTH_AUDIENCE, "POST", path, body),
                "content-type": "application/json",
            },
        )
        return status, raw, dict(headers)

    def reverse(rev):
        status, body, _ = health("/health/context", rev.content)
        if status == 200 and json.loads(rev.content)["operation"] == "profile":
            state["projection"] = json.loads(body)
        return httpx.Response(
            status, content=body, headers={"content-type": "application/json"}
        )

    def current(binding, phase, nonce):
        status, raw, _ = health(
            "/health/current",
            canonical(
                {
                    "binding": binding.decode(),
                    "phase": phase,
                    "nonce": nonce,
                }
            ),
        )
        state["phases"].append([phase, nonce, status])
        if status != 200:
            return {}
        return json.loads(raw)

    with pytest.MonkeyPatch.context() as monkeypatch:
        offline_startup_mutation_inventory.__wrapped__(
            SimpleNamespace(node=SimpleNamespace(get_closest_marker=lambda _: None)),
            monkeypatch,
        )
        host = setup.__wrapped__(directory, monkeypatch)(
            subject=config["subject"],
            database=db,
            reverse_transport=reverse,
            verify_transaction=lambda req, raw, nonce: (
                len(req.headers.getlist(PROOF_HEADER)) == 1
                and verify(
                    key,
                    PAS_AUDIENCE,
                    req.method,
                    req.url.path,
                    raw,
                    req.headers.get(PROOF_HEADER),
                )
                == nonce
            ),
            health_binding=config["health_binding"],
            runtime_options={"model": "fake", "maximum_sensitivity": "restricted"},
        )
        host.authority.clock = clock

        def issue(conn, method, path, body=None, headers=None, **kwargs):
            if conn.port == receiver_port and method == "POST":
                if config.get("fault") == "pas-after-fence":
                    raise OSError("synthetic interruption before the first HTTP write")
                state["issued"].append(
                    {
                        "path": path,
                        "attempt": headers["X-PAS-Attempt"],
                        "digest": digest(body),
                    }
                )
            return original_request(
                conn, method, path, body=body, headers=headers, **kwargs
            )

        original_request = http.client.HTTPConnection.request
        monkeypatch.setattr(http.client.HTTPConnection, "request", issue)
        witness = PlanWitness(directory / "root-witness.json", db)
        host.fixture.service.attempts = native_attempts(db, witness)
        if config.get("fault") == "pas-root-failure":

            def fail_root(**_):
                raise OSError("synthetic interruption before native root commit")

            host.fixture.service.attempts.claim_binding = fail_root
        host.directory.recovery_current = witness.current
        installation = host.target.bridge.installation
        receiver = LoopbackReceiver(
            receiver_port,
            Ed25519PublicKey.from_public_bytes(
                bytes.fromhex(config["receiver_key"]),
            ),
        )
        preview_key, release_key, terminal_key = (
            Ed25519PrivateKey.generate() for _ in range(3)
        )
        runtime = RuntimeDispatch(
            destination=Destination(
                account=installation.registration_binding,
                connection=str(installation.connection_id),
                endpoint="loopback-fixture",
                model="fake",
                provider="fake",
                revision=installation.connection_revision,
                runtime=str(installation.runtime_id),
            ),
            receiver=receiver,
            pas_issuer="pas-health-paired",
            release_kid="release",
            release_key=release_key.public_key(),
            issuer="runtime-health-paired",
            terminal_kid="terminal",
            terminal_key=terminal_key,
        )

        def memory_grants():
            snapshot = host.target.memory
            with application_scope_context(
                ApplicationScope(application_id="personal_ai")
            ):
                lifecycle = host.fixture.lifecycle.get_state(
                    owner_id=host.principal.owner_id,
                    memory_id=snapshot.id,
                )
            dep = memory_dependency(
                snapshot, lifecycle, acting_user_id=host.enrollment.actor
            )
            return {"approved-pas-memory-origin": dep.version} | {
                name: grant.dependency(dep, name).version
                for name, grant in zip(
                    ("runtime-handoff", "inference-disclosure"),
                    host.fixture.disclosures[host.target.plan.scope],
                    strict=True,
                )
            }

        def memory_commit(grants):
            return hmac.digest(
                memory_key,
                canonical(
                    {
                        "id": str(host.target.memory.id),
                        "grants": grants,
                    }
                ),
                "sha256",
            ).hex()

        def commitments(frozen):
            state["dependencies"][str(frozen.original_key)] = frozen
            source = next(
                item
                for item in frozen.snapshots
                if item.provider_id == host.target.plan.source_provider_id
            )
            memory = next(
                item for item in frozen.snapshots if item.provider_id == "ai_memory"
            )
            projection = state["projection"]
            assert source.source_version == str(
                projection["items"][0]["object_revision"]
            )
            grants = {
                dep.purpose: dep.version for dep in memory.permission_dependencies
            }
            bound = config["health_binding"]
            return hmac.digest(
                projection_key,
                canonical(
                    {
                        "profile": projection,
                        "owner": bound["owner"],
                        "enrollment": bound["enrollment_id"],
                        "enrollment_version": 1,
                        "consent_epoch": 1,
                        "erasure_epoch": 0,
                        "lifecycle": "active",
                    }
                ),
                "sha256",
            ).hex(), memory_commit(grants)

        def preview_expiry(receipt, frozen):
            encoded, signature = map(decode, receipt.split("."))
            host.verify_keys[KEY_ID].verify(signature, encoded)
            claims = json.loads(encoded)
            assert claims["response_digest"] == digest(frozen.attested_body)
            return claims["exp"]

        journal = SyntheticDispatchJournal(directory / "journal")
        registration = DispatchRegistration(
            host.target.plan,
            TENANT,
            config["health_binding"]["installation_id"],
            runtime,
            CurrentSource(current),
            verified_create=lambda conversation, original: state["creates"].get(
                (conversation, original)
            ),
            source_commitments=commitments,
            verified_preview_expiry=preview_expiry,
            load_dependencies=lambda binding: state["dependencies"].get(
                binding.original_key
            ),
            trust_current=lambda: True,
            receipt_authority=host.authority,
        )
        dispatch = PrivateDispatch(
            plans=host.fixture.service,
            journal=journal,
            registrations=(registration,),
            issuer="pas-health-paired",
            preview_kid="preview",
            preview_key=preview_key,
            release_key=release_key,
            continuity_current=witness.current,
            clock=clock,
        )
        for route in host.app.state.private_application_plan_routes:
            host.app.router.routes.remove(route)
        host.app.state.private_application_plan_routes = ()
        host.fixture.mount(dispatch=dispatch)

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        server = uvicorn.Server(
            uvicorn.Config(
                host.app,
                lifespan="on",
                access_log=False,
                server_header=False,
                log_level="error",
            )
        )
        thread = Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        while not server.started and thread.is_alive():
            sleep(0.01)
        assert server.started
        cid = None
        original = None
        branch = None
        scope = host.target.plan.scope
        output(
            {
                "port": sock.getsockname()[1],
                "pid": os.getpid(),
                "now": start,
                "owner": host.principal.owner_id,
                "issuer": host.principal.issuer,
                "subject": host.principal.subject,
                "actor": host.enrollment.actor,
                "client": host.namespace,
                "target": host.enrollment.target_id,
                "policy": host.enrollment.policy_epoch,
                "source_epoch": host.enrollment.source_epoch,
                "recipient_digest": host.target.plan.preview_binding(
                    host.principal, UUID(int=0)
                ).target_fingerprint,
                "auth": host.headers["authorization"],
                "original_kid": KEY_ID,
                "wrong_auth": "Bearer "
                + host.bearer(AUDIENCE, subject=host.principal.subject + "-other"),
                "old_key": host.verify_keys[KEY_ID].public_bytes_raw().hex(),
                "preview_key": preview_key.public_key().public_bytes_raw().hex(),
                "terminal_key": terminal_key.public_key().public_bytes_raw().hex(),
                "destination": runtime.destination.model_dump(mode="json"),
                "selection": host.enrollment.selected.request("profile"),
                "stores": {
                    "canonical": str(journal._path),
                    "runtime": str(host.target.store._send_fence_directory()),
                    "root_witness": str(witness.path),
                },
                "native_backend": {
                    "principal": type(host.directory).__name__,
                    "memory": type(host.fixture.memories).__name__,
                    "message_history": type(host.messages).__name__,
                    "conversation": type(host.fixture.host.conversations).__name__,
                },
            }
        )
        for line in sys.stdin:
            operation, values = json.loads(line)
            if operation == "create-proof":
                _, headers = prepare(host, values["body"], expires=start + 30)
                output({"headers": headers})
            elif operation == "setup-preview":
                cid = UUID(values["conversation"])
                original = UUID(values["original"])
                create = UUID(values["create"])
                raw = values["create_response"].encode()
                signed, sig = map(decode, values["create_header"].split("."))
                host.verify_keys[KEY_ID].verify(sig, signed)
                claims = json.loads(signed)
                assert claims["response_digest"] == digest(raw)
                assert claims["original_key"] == str(create) and claims[
                    "conversation_id"
                ] == str(cid)
                state["creates"][cid, original] = CreateBinding(
                    create,
                    values["create_header"],
                    1,
                    claims["exp"],
                )
                branch = configure_preview(
                    host, cid, branch_id=UUID(values["branch_id"])
                )
                _, headers = prepare(
                    host,
                    {
                        "idempotency_key": str(original),
                        "choice": {"mode": "user_owned_plan"},
                        "content": CONTENT,
                    },
                    cid=cid,
                    create_key=create,
                    branch=branch,
                    expires=start + 30,
                )
                grants = memory_grants()
                output(
                    {
                        "headers": headers,
                        "branch": branch,
                        "memory_id": str(host.target.memory.id),
                        "memory_grants": grants,
                        "memory_commitment": memory_commit(grants),
                        "source_grants": {
                            name: grant.version
                            for (_, name), grant in host.grants.items()
                        },
                    }
                )
            elif operation == "revoke":
                if values["kind"] == "pas-memory":
                    host.fixture.disclosures[scope] = ()
                elif values["kind"] == "pas-source":
                    host.grants.pop((cid, "inference-disclosure"))
                elif values["kind"] == "pas-release":
                    dispatch.retire(registration, cid, original)
                elif values["kind"] == "pas-owner":
                    host.current.clear()
                output({"ok": True})
            elif operation == "report":
                row = journal.read(dispatch.key(registration, cid, original))
                root = UUID(row.binding.root) if row else None
                root_present = (
                    host.fixture.service.attempts.binding_exists(
                        owner=host.principal.owner_id,
                        root=root,
                    )
                    if root
                    else False
                )
                output(
                    {
                        "issued": state["issued"],
                        "phases": state["phases"],
                        "state": row.state if row else None,
                        "root": str(root) if root else None,
                        "native_root": root_present,
                        "physical_fences": len(
                            list(host.target.store._send_fence_directory().glob("*"))
                        ),
                        "body_digest": row.body_hash if row else None,
                        "branch": branch,
                        "network_denials": attempts,
                    }
                )
            elif operation == "stop":
                server.should_exit = True
                thread.join(4)
                output({"stopped": not thread.is_alive()})
                break
            else:
                raise RuntimeError("unexpected PAS control operation")
        db.close()


if __name__ == "__main__":
    main(json.loads(sys.stdin.readline()))
