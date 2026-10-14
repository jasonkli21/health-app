from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql

from health_api.application.personal_ai_federation_export import (
    HealthFederationExportDenied,
    read_health_federation_export,
)
from health_api.integrations.federation_export import HealthFederationExportRequest

OWNER_ID = UUID("00000000-0000-0000-0000-000000000929")


class _FakeResult:
    def __init__(self, row) -> None:
        self.row = row

    def one_or_none(self):
        return self.row


class _QueryCheckingSession:
    """Return a fixture row only after checking the generated owner/policy query."""

    def __init__(self, row) -> None:
        self.row = row
        self.statement = None

    def execute(self, statement):
        compiled = statement.compile(dialect=postgresql.dialect())
        sql = str(compiled).lower()
        assert "health_objects.owner_id =" in sql
        assert "health_objects.cross_domain_use_allowed is true" in sql
        assert OWNER_ID in compiled.params.values()
        self.statement = statement
        return _FakeResult(self.row)


def _request(entity_id: UUID, *, operation: str = "read") -> HealthFederationExportRequest:
    return HealthFederationExportRequest(
        operation=operation,
        category="dietary_restrictions",
        entity_id=entity_id,
        purpose="health_dietary_restrictions_to_travel",
        destination_application_id="travel",
        fields=("permission_version",) if operation == "verify" else ("dietary_restrictions",),
    )


def _row(entity_id: UUID, value: object):
    source_id = uuid4()
    return (
        SimpleNamespace(
            id=entity_id,
            revision=3,
            ai_use_allowed=True,
            cross_domain_use_allowed=True,
            schema_version=1,
        ),
        SimpleNamespace(
            payload={
                "kind": "constraint",
                "category": "constraints",
                "key": "dietary_restrictions",
                "label": "Dietary restrictions",
                "value": value,
            }
        ),
        SimpleNamespace(id=source_id),
    )


def test_health_federation_export_is_a_narrow_complete_source_projection() -> None:
    entity_id = uuid4()
    session = _QueryCheckingSession(
        _row(entity_id, {"type": "text_list", "value": ["synthetic allergy"]})
    )

    response = read_health_federation_export(
        session, OWNER_ID, _request(entity_id), now=datetime(2026, 10, 11, tzinfo=UTC)
    )

    assert response.complete is True
    assert response.authoritative_empty is False
    assert response.continuation is None
    assert response.item.payload.model_dump() == {"dietary_restrictions": ("synthetic allergy",)}
    assert response.item.source_revision == 3
    assert response.item.sensitivity == "restricted"
    assert len(response.item.permission_dependencies) == 1
    assert response.item.permission_dependencies[0].destination_application_id == "travel"
    assert {ref.kind for ref in response.item.source_refs} == {"record", "source"}


def test_health_federation_export_keeps_authoritative_empty_and_verifies_current_revision() -> None:
    entity_id = uuid4()
    empty = read_health_federation_export(
        _QueryCheckingSession(_row(entity_id, None)),
        OWNER_ID,
        _request(entity_id),
        now=datetime(2026, 10, 11, tzinfo=UTC),
    )
    assert empty.complete is True
    assert empty.authoritative_empty is True
    assert empty.item.payload.model_dump() == {"dietary_restrictions": None}

    verified = read_health_federation_export(
        _QueryCheckingSession(_row(entity_id, None)),
        OWNER_ID,
        _request(entity_id, operation="verify"),
        now=datetime(2026, 10, 11, tzinfo=UTC),
    )
    assert verified.operation == "verify"
    assert verified.item.source_revision == 3
    assert verified.item.payload is None


def test_health_federation_export_denies_missing_revoked_or_unsupported_values() -> None:
    entity_id = uuid4()
    with pytest.raises(HealthFederationExportDenied, match="health_federation_export_denied"):
        read_health_federation_export(_QueryCheckingSession(None), OWNER_ID, _request(entity_id))

    unsupported = _QueryCheckingSession(_row(entity_id, {"type": "boolean", "value": True}))
    with pytest.raises(HealthFederationExportDenied, match="value_type_unsupported"):
        read_health_federation_export(unsupported, OWNER_ID, _request(entity_id))
