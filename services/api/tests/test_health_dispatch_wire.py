from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from health_api.integrations.pas_dispatch import (
    Binding,
    PinnedKey,
    digest,
    verify_detail,
    verify_preview,
    verify_status,
)
from health_api.integrations.personal_ai_preview_receipt import canonical_json

FIXTURES = Path(__file__).parent / "fixtures" / "pas_dispatch"


def vector(domain: str) -> tuple[bytes, bytes, bytes, bytes, bytes, bytes]:
    keys, payload, binding, preview, confirmation, terminal, signature = (
        (FIXTURES / f"{domain}.txt").read_bytes().splitlines()
    )
    envelope = canonical_json(
        {
            "claims": json.loads(preview),
            "signature": json.loads(confirmation)["preview_sig"],
        }
    )
    return (
        keys,
        payload,
        binding,
        envelope,
        confirmation,
        canonical_json(
            {
                "state": "completed",
                "original_key": json.loads(binding)["original_key"],
                "attempt": json.loads(binding)["attempt"],
                "root": json.loads(binding)["root"],
                "body_sha256": digest(confirmation),
                "message_id": json.loads(terminal)["message_id"],
                "terminal": json.loads(terminal),
                "signature": signature.decode("ascii"),
            }
        ),
    )


def public_key(encoded: str) -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(base64.urlsafe_b64decode(encoded + "="))


@pytest.mark.parametrize("domain", ["health", "travel"])
def test_golden_raw_transcript(domain: str) -> None:
    keys, payload, raw, envelope, confirmation, status = vector(domain)
    pas, runtime = [public_key(key) for key in json.loads(keys)]
    binding = Binding(raw)
    preview_key = PinnedKey("pas-fixture", "preview", domain, "p1", pas, lambda: True)
    terminal_key = PinnedKey(
        "runtime-fixture", "terminal", "pas-fixture", "r1", runtime, lambda: True
    )
    preview = verify_preview(envelope, binding, preview_key, 1000)
    assert preview.confirmation_body == confirmation
    assert preview.payload_digest == digest(payload)
    assert preview.payload_digest != digest(payload + b" ")
    with pytest.raises(ValueError):
        verify_preview(envelope, binding, preview_key, 1060)
    with pytest.raises(ValueError):
        verify_preview(envelope + b"\n", binding, preview_key, 1000)
    with pytest.raises(ValueError):
        verify_preview(
            envelope.replace(b"pas-dispatch/1", b"pas-dispatch/2"), binding, preview_key, 1000
        )
    with pytest.raises(ValueError):
        Binding(raw.replace(b'"epoch":1', b'"epoch":1,"epoch":1'))

    terminal = verify_status(
        status,
        binding=binding,
        body_digest=digest(confirmation),
        trust=terminal_key,
        now=1001,
    )
    assert terminal is not None
    fields = binding.fields
    detail = {
        **{name: fields[name] for name in ("attempt", "root", "original_key")},
        "message_id": terminal.message_id,
        "result": "ok",
    }
    assert verify_detail(canonical_json(detail), binding, terminal) == "ok"
    with pytest.raises(ValueError):
        verify_detail(canonical_json(detail | {"result": "wrong"}), binding, terminal)
    with pytest.raises(ValueError):
        verify_status(
            status,
            binding=binding,
            body_digest=digest(confirmation),
            trust=terminal_key,
            now=1100,
        )


def test_cross_signature_recipient_and_epoch_refused() -> None:
    keys, _, raw, envelope, _, _ = vector("health")
    other = json.loads(vector("travel")[3])["signature"]
    key = PinnedKey(
        "pas-fixture", "preview", "health", "p1", public_key(json.loads(keys)[0]), lambda: True
    )
    value = json.loads(envelope)
    with pytest.raises(ValueError):
        verify_preview(canonical_json(value | {"signature": other}), Binding(raw), key, 1000)
    for changed in (
        raw.replace(b'"fixture"', b'"another"'),
        raw.replace(b'"epoch":1', b'"epoch":2'),
    ):
        with pytest.raises(ValueError):
            verify_preview(envelope, Binding(changed), key, 1000)
