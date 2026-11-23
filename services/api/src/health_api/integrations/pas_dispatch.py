"""Closed, synthetic pas-dispatch/1 wire profile for Health."""

from __future__ import annotations

import base64
import re
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from typing import Any
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from health_api.integrations.personal_ai_preview_receipt import canonical_json, strict_object

VERSION = "pas-dispatch/1"
MEDIA_TYPE = "application/vnd.pas.dispatch-v1+json"
PREVIEW_HEADER = "x-pas-dispatch-receipt"
ORIGINAL_KEY_HEADER = "X-PAS-Original-Key"
MAX_RESPONSE = 32768
_BINDING_DIGESTS = ("branch", "create_receipt", "memory", "preview_receipt", "source")
_BINDING_UUIDS = ("attempt", "conversation", "create_key", "original_key", "root")
_BINDING_NAMES = (
    "actor_issuer",
    "app",
    "client",
    "installation",
    "owner",
    "policy",
    "subject",
    "target",
    "tenant",
)
_DESTINATION_NAMES = ("account", "connection", "endpoint", "model", "provider", "runtime")
_STATES = {"unknown", "claimed", "send_started", "completed", "quarantined"}


def digest(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def receipt_digest(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
        raise ValueError("invalid original receipt header")
    return digest(value.encode("ascii"))


def is_digest(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def is_epoch(value: object) -> bool:
    return type(value) is int and 0 <= value <= 2**53 - 1


def _name(value: object) -> bool:
    return isinstance(value, str) and 0 < len(value.encode("utf-8")) <= 256


def _uuid(value: object) -> bool:
    return isinstance(value, str) and str(UUID(value)) == value


def _shape(value: object, names: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or value.keys() != names:
        raise ValueError("invalid dispatch shape")
    return value


def _token(value: str, length: int) -> bytes:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("invalid dispatch encoding")
    raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    if len(raw) != length or base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=") != value:
        raise ValueError("invalid dispatch encoding")
    return raw


def _object(raw: bytes) -> dict[str, Any]:
    # This closed ABI uses only fixed ASCII member names, strings, safe integers and null.
    # The existing encoder is JCS-equivalent for those types and rejects surrogate scalars.
    return strict_object(raw, MAX_RESPONSE)


@dataclass(frozen=True)
class Binding:
    raw: bytes

    def __post_init__(self) -> None:
        if type(self.raw) is not bytes:
            raise ValueError("dispatch binding must be immutable bytes")
        value = _shape(
            _object(self.raw),
            {
                *_BINDING_DIGESTS,
                *_BINDING_UUIDS,
                *_BINDING_NAMES,
                "destination",
                "epoch",
                "workspace",
            },
        )
        dest = _shape(value["destination"], {*_DESTINATION_NAMES, "revision"})
        if (
            not all(is_digest(value[key]) for key in _BINDING_DIGESTS)
            or not all(_uuid(value[key]) for key in _BINDING_UUIDS)
            or not all(_name(value[key]) for key in _BINDING_NAMES)
            or not all(_name(dest[key]) for key in _DESTINATION_NAMES)
            or not is_epoch(value["epoch"])
            or not is_epoch(dest["revision"])
            or (value["workspace"] is not None and not _name(value["workspace"]))
        ):
            raise ValueError("invalid dispatch binding")

    @property
    def fields(self) -> dict[str, Any]:
        # Return a fresh object. The validated bytes are the source of truth.
        return _object(self.raw)

    @property
    def sha256(self) -> str:
        return digest(self.raw)


@dataclass(frozen=True)
class PinnedKey:
    issuer: str
    purpose: str
    audience: str
    kid: str
    key: Ed25519PublicKey
    active: Callable[[], bool]

    def verify(self, raw: bytes, signature: str, now: int) -> dict[str, Any]:
        # Signature verification precedes all comparisons against authorization fields.
        try:
            if not self.active():
                raise ValueError("inactive dispatch key")
            self.key.verify(_token(signature, 64), raw)
        except InvalidSignature:
            raise ValueError("invalid dispatch signature") from None
        claims = _object(raw)
        if (
            (
                claims.get("issuer"),
                claims.get("purpose"),
                claims.get("audience"),
                claims.get("kid"),
                claims.get("v"),
            )
            != (self.issuer, self.purpose, self.audience, self.kid, VERSION)
            or not is_epoch(claims.get("expires"))
            or not is_epoch(now)
            or now >= claims["expires"]
        ):
            raise ValueError("invalid dispatch claims")
        return claims


@dataclass(frozen=True)
class VerifiedPreview:
    expires: int
    confirmation_body: bytes
    claims_digest: str
    payload_digest: str


def verify_preview(raw: bytes, binding: Binding, trust: PinnedKey, now: int) -> VerifiedPreview:
    if trust.purpose != "preview" or trust.audience != binding.fields["app"]:
        raise ValueError("wrong dispatch preview key")
    envelope = _shape(_object(raw), {"claims", "signature"})
    statement = canonical_json(envelope["claims"])
    signature = envelope["signature"]
    claims = trust.verify(statement, signature, now)
    _shape(
        claims,
        {
            "issuer",
            "purpose",
            "audience",
            "kid",
            "v",
            "expires",
            "binding_sha256",
            "payload_sha256",
        },
    )
    if (
        claims["binding_sha256"] != binding.sha256
        or not is_digest(claims["payload_sha256"])
        or claims["expires"] > now + 60
    ):
        raise ValueError("dispatch preview binding mismatch")
    confirmation = digest(statement)
    body = canonical_json(
        {
            "confirmation": confirmation,
            "original_key": binding.fields["original_key"],
            "preview_sig": signature,
            "v": VERSION,
        }
    )
    return VerifiedPreview(claims["expires"], body, confirmation, claims["payload_sha256"])


@dataclass(frozen=True)
class Terminal:
    message_id: str
    result_sha256: str
    expires: int


class DispatchEvidenceConflict(ValueError):
    """A complete response contradicts the original attempt or its terminal."""


def verify_status(
    raw: bytes,
    *,
    binding: Binding,
    body_digest: str,
    trust: PinnedKey,
    now: int,
) -> Terminal | None:
    status = _shape(
        _object(raw),
        {
            "state",
            "original_key",
            "attempt",
            "root",
            "body_sha256",
            "message_id",
            "terminal",
            "signature",
        },
    )
    fields = binding.fields
    if (
        status["state"] not in _STATES
        or any(status[field] != fields[field] for field in ("original_key", "attempt", "root"))
        or (
            status["body_sha256"] != body_digest
            and (status["state"], status["body_sha256"]) != ("unknown", None)
        )
    ):
        raise DispatchEvidenceConflict("dispatch status binding mismatch")
    if status["state"] != "completed":
        if any(status[name] is not None for name in ("message_id", "terminal", "signature")):
            raise DispatchEvidenceConflict("nonterminal response carries content")
        if status["state"] == "quarantined":
            raise DispatchEvidenceConflict("dispatch status quarantined")
        return None
    if trust.purpose != "terminal":
        raise DispatchEvidenceConflict("wrong dispatch terminal key")
    try:
        claims = trust.verify(canonical_json(status["terminal"]), status["signature"], now)
    except ValueError:
        raise DispatchEvidenceConflict("dispatch terminal signature or expiry invalid") from None
    if (
        set(claims)
        != {
            "issuer",
            "purpose",
            "audience",
            "kid",
            "v",
            "expires",
            "attempt",
            "root",
            "message_id",
            "binding_sha256",
            "body_sha256",
            "result_sha256",
        }
        or not _uuid(claims["message_id"])
        or claims["message_id"] != status["message_id"]
        or claims["attempt"] != fields["attempt"]
        or claims["root"] != fields["root"]
        or claims["binding_sha256"] != binding.sha256
        or claims["body_sha256"] != body_digest
        or not is_digest(claims["result_sha256"])
    ):
        raise DispatchEvidenceConflict("dispatch terminal binding mismatch")
    return Terminal(claims["message_id"], claims["result_sha256"], claims["expires"])


def verify_detail(raw: bytes, binding: Binding, terminal: Terminal) -> str:
    detail = _object(raw)
    fields = binding.fields
    result = detail.get("result")
    if (
        set(detail) != {"message_id", "attempt", "root", "original_key", "result"}
        or detail["message_id"] != terminal.message_id
        or any(detail[name] != fields[name] for name in ("attempt", "root", "original_key"))
        or not isinstance(result, str)
        or digest(result.encode("utf-8")) != terminal.result_sha256
    ):
        raise DispatchEvidenceConflict("dispatch detail binding mismatch")
    return result
