"""Strict encoding and Health-side verification for the isolated preview protocol."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from collections.abc import Mapping
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

RECEIPT_ISSUER = "urn:fixture:pas:health-preview"
RECEIPT_AUDIENCE = "urn:fixture:health:preview-receipt"
RECEIPT_LIFETIME_SECONDS = 30
MAX_RECEIPT_BYTES = 8192
MAX_RESPONSE_BYTES = 16384
PROFILE_PATH = "/private/application-plan/v1/conversations"


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def canonical_digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def strict_object(raw: bytes, max_bytes: int, *, canonical: bool = True) -> dict[str, Any]:
    if len(raw) > max_bytes:
        raise ValueError("oversized JSON")
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
    if not isinstance(value, dict) or (canonical and canonical_json(value) != raw):
        raise ValueError("noncanonical JSON object")
    return value


def _decode(segment: str) -> bytes:
    raw = base64.b64decode(segment + "=" * (-len(segment) % 4), altchars=b"-_", validate=True)
    if base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=") != segment:
        raise ValueError("noncanonical receipt encoding")
    return raw


def verify_health_preview_receipt(
    header: str,
    response: bytes,
    *,
    expected: Mapping[str, object],
    keys: Mapping[str, Ed25519PublicKey],
    now: int,
) -> dict[str, Any]:
    """Verify an exact receipt against caller-authorized claims and the received bytes."""
    if len(header) > MAX_RECEIPT_BYTES or len(response) > MAX_RESPONSE_BYTES:
        raise ValueError("oversized preview receipt or response")
    try:
        encoded, signature = header.split(".")
        statement = _decode(encoded)
        claims = strict_object(statement, MAX_RECEIPT_BYTES)
        issued, expires = claims["iat"], claims["exp"]
        kid = claims["kid"]
        if (
            not isinstance(kid, str)
            or type(issued) is not int
            or type(expires) is not int
            or not issued <= now < expires <= issued + RECEIPT_LIFETIME_SECONDS
            or canonical_json(claims)
            != canonical_json(
                {
                    **expected,
                    "alg": "Ed25519",
                    "kid": kid,
                    "iss": RECEIPT_ISSUER,
                    "aud": RECEIPT_AUDIENCE,
                    "iat": issued,
                    "exp": expires,
                    "response_digest": hashlib.sha256(response).hexdigest(),
                }
            )
        ):
            raise ValueError("preview receipt binding mismatch")
        keys[kid].verify(_decode(signature), statement)
        return claims
    except (KeyError, TypeError, InvalidSignature, UnicodeError, binascii.Error, RecursionError):
        raise ValueError("invalid preview receipt") from None
