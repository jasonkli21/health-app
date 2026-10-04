"""Real pinned Firebase Admin verification with local RSA certificate fixtures."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import firebase_admin
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from firebase_admin import auth, credentials
from google.auth import crypt, jwt
from google.auth.credentials import AnonymousCredentials
from health_api.integrations.firebase_auth import (
    FirebaseTokenVerifier,
    TokenVerificationError,
    VerifierUnavailable,
)


class LocalCredential(credentials.Base):
    def get_credential(self):
        return AnonymousCredentials()


@pytest.fixture
def signed_verifier(monkeypatch):
    monkeypatch.delenv("FIREBASE_AUTH_EMULATOR_HOST", raising=False)
    project = "health-crypto-test"
    verifier = FirebaseTokenVerifier(project, timeout_seconds=2, max_in_flight=2)
    verifier._app_name = f"crypto-{uuid4()}"
    app = firebase_admin.initialize_app(
        LocalCredential(), options={"projectId": project}, name=verifier._app_name
    )
    client = auth._get_client(app)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "local-test")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    signer = crypt.RSASigner.from_string(pem, key_id="local-key")
    certs = {"local-key": cert.public_bytes(serialization.Encoding.PEM).decode()}

    def certificate_request(*args, **kwargs):
        return SimpleNamespace(status=200, data=json.dumps(certs).encode())

    client._token_verifier.request = certificate_request
    users = {}

    def user_response(uid):
        return users.get(uid, {"localId": uid, "validSince": "0", "disabled": False})

    monkeypatch.setattr(client._user_manager, "get_user", lambda *, uid: user_response(uid))

    def token(subject="first", **overrides):
        issued = int(time.time()) - 1
        claims = {
            "iss": f"https://securetoken.google.com/{project}",
            "aud": project,
            "sub": subject,
            "iat": issued,
            "auth_time": issued,
            "exp": issued + 3600,
        }
        claims.update(overrides)
        return jwt.encode(signer, claims).decode()

    yield verifier, token, users, client
    firebase_admin.delete_app(app)


def test_signed_sdk_fixture_is_verified(signed_verifier):
    verifier, token, _, _ = signed_verifier
    assert verifier.verify(token()).subject == "first"


@pytest.mark.parametrize(
    "change", ["signature", "expiry", "issuer", "audience", "revoked", "disabled"]
)
def test_real_sdk_rejects_invalid_crypto_and_account_state(signed_verifier, change):
    verifier, token, users, _ = signed_verifier
    value = token()
    if change == "signature":
        head, payload, signature = value.split(".")
        value = f"{head}.{payload}.{'A' if signature[0] != 'A' else 'B'}{signature[1:]}"
    elif change == "expiry":
        value = token(iat=int(time.time()) - 7200, exp=int(time.time()) - 3600)
    elif change == "issuer":
        value = token(iss="https://securetoken.google.com/foreign")
    elif change == "audience":
        value = token(aud="foreign")
    elif change == "revoked":
        users["first"] = {"localId": "first", "validSince": str(int(time.time()) + 1)}
    elif change == "disabled":
        users["first"] = {"localId": "first", "disabled": True}
    with pytest.raises(TokenVerificationError):
        verifier.verify(value)


def test_real_sdk_certificate_outage_is_sanitized(signed_verifier):
    verifier, token, _, client = signed_verifier
    from google.auth.exceptions import TransportError

    def outage(*args, **kwargs):
        raise TransportError("private certificate service details")

    client._token_verifier.request = outage
    with pytest.raises(VerifierUnavailable):
        verifier.verify(token())


def test_signed_two_subjects_resolve_distinct_owners_and_isolate_all_routes(
    signed_verifier, postgres_engine, db_session
):
    from fastapi.testclient import TestClient
    from health_api.config.settings import Settings
    from health_api.main import create_app
    from health_api.persistence.models import ProviderIdentity
    from sqlalchemy import select
    from test_daily_api import event_request, meal_event, observation
    from test_profile_api import request_body

    verifier, token, _, _ = signed_verifier
    settings = Settings(
        _env_file=None,
        app_env="test",
        auth_mode="firebase",
        firebase_project_id="health-crypto-test",
    )
    client = TestClient(create_app(settings, engine=postgres_engine, identity_verifier=verifier))
    headers = {
        subject: {"Authorization": f"Bearer {token(subject, email='same@example.test')}"}
        for subject in ("first", "second")
    }
    resources = [
        ("profile", request_body()),
        ("events", event_request(meal_event("date_only"))),
        ("observations", {"id": str(uuid4()), "observation": observation("weight", 70, "kg")}),
    ]
    ids = []
    for resource, body in resources:
        created = client.post(f"/{resource}", json=body, headers=headers["first"])
        assert created.status_code == 201, created.text
        item = created.json()
        ids.append(item["id"])
        path = f"/{resource}/{item['id']}"
        assert client.get(path, headers=headers["first"]).status_code == 200
        assert client.get(path + "/history", headers=headers["first"]).status_code == 200
        assert client.get(path, headers=headers["second"]).status_code == 404
        assert client.get(path + "/history", headers=headers["second"]).status_code == 404
        update = {"expected_revision": 1}
        update.update(
            {key: body[key] for key in ("profile", "event", "observation") if key in body}
        )
        assert client.patch(path, json=update, headers=headers["second"]).status_code == 404
        assert (
            client.delete(
                path, params={"expected_revision": 1}, headers=headers["second"]
            ).status_code
            == 404
        )
        own_list = client.get(f"/{resource}", headers=headers["first"])
        foreign_list = client.get(f"/{resource}", headers=headers["second"])
        assert own_list.status_code == foreign_list.status_code == 200
        assert item["id"] in {entry["id"] for entry in own_list.json()["items"]}
        assert foreign_list.json()["items"] == []
    first_day = client.get(
        "/today",
        params={"date": "2026-05-01", "timezone": "America/Los_Angeles"},
        headers=headers["first"],
    )
    second_day = client.get(
        "/today",
        params={"date": "2026-05-01", "timezone": "America/Los_Angeles"},
        headers=headers["second"],
    )
    assert first_day.status_code == second_day.status_code == 200
    assert any(item_id in first_day.text for item_id in ids[1:])
    assert all(item_id not in second_day.text for item_id in ids)
    mappings = list(db_session.scalars(select(ProviderIdentity)))
    assert {entry.subject for entry in mappings} == {"first", "second"}
    assert len({entry.user_id for entry in mappings}) == 2
    # A valid token refresh reuses the stable provider mapping.
    client.get("/profile", headers={"Authorization": f"Bearer {token('first')}"})
    assert len(list(db_session.scalars(select(ProviderIdentity)))) == 2
