from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from health_api.application import analytics_service
from health_api.application.analytics_contracts import (
    AnalyticsConflict,
    ArtifactAggregate,
)
from health_api.config.settings import Settings
from health_api.main import create_app
from health_api.persistence.models import (
    AnalyticsArtifact,
    AnalyticsEvidence,
    HealthObject,
    User,
)
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session

OWNER_ID = UUID("00000000-0000-0000-0000-000000000909")
OTHER_OWNER_ID = UUID("00000000-0000-0000-0000-000000000919")
ANALYSIS_DATE = date(2026, 10, 7)


@pytest_asyncio.fixture
async def analytics_client(
    db_session: Session, postgres_engine: Engine
) -> AsyncIterator[AsyncClient]:
    settings = Settings(
        _env_file=None,
        app_env="test",
        auth_mode="dev",
        local_principal_id=OWNER_ID,
        local_principal_timezone="America/Los_Angeles",
    )
    app = create_app(settings, engine=postgres_engine)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


def _energy_event() -> dict[str, object]:
    return {
        "domain": "nutrition",
        "time": {
            "precision": "date_only",
            "local_date": ANALYSIS_DATE.isoformat(),
            "timezone": "America/Los_Angeles",
        },
        "ended_at": None,
        "payload": {
            "kind": "meal",
            "label": "Synthetic analytics regression meal",
            "foods": ["synthetic oats"],
            "energy": {"value": 215, "unit": "kcal"},
        },
        "notes": None,
    }


async def _create_energy_event(client: AsyncClient, object_id: UUID) -> None:
    response = await client.post(
        "/events",
        json={"id": str(object_id), "event": _energy_event(), "ai_use_allowed": True},
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_analytics_artifact_records_exact_owner_and_source_revision(
    analytics_client: AsyncClient,
    db_session: Session,
) -> None:
    event_id = uuid4()
    await _create_energy_event(analytics_client, event_id)

    signal = analytics_service.compute_trend(
        db_session,
        OWNER_ID,
        "energy",
        ANALYSIS_DATE,
        ANALYSIS_DATE,
        "America/Los_Angeles",
    )

    assert signal.result.evidence_refs[0].object_id == event_id
    assert signal.result.evidence_refs[0].revision == 1
    evidence = db_session.scalar(
        select(AnalyticsEvidence).where(
            AnalyticsEvidence.owner_id == OWNER_ID,
            AnalyticsEvidence.artifact_object_id == signal.obj.id,
        )
    )
    assert evidence is not None
    assert evidence.evidence_object_id == event_id
    assert evidence.evidence_revision == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("changed_source", ["generation", "revision"])
async def test_analytics_persist_rejects_changed_snapshot_evidence(
    analytics_client: AsyncClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    changed_source: str,
) -> None:
    event_id = uuid4()
    await _create_energy_event(analytics_client, event_id)
    persist_signal = analytics_service._persist_signal

    def change_then_persist(
        session: Session,
        owner_id: UUID,
        **kwargs: Any,
    ) -> ArtifactAggregate:
        if changed_source == "generation":
            session.execute(
                update(User)
                .where(User.id == owner_id)
                .values(daily_sequence=User.daily_sequence + 1)
            )
        else:
            session.execute(
                update(HealthObject)
                .where(HealthObject.owner_id == owner_id, HealthObject.id == event_id)
                .values(revision=HealthObject.revision + 1)
            )
        return persist_signal(session, owner_id, **kwargs)

    monkeypatch.setattr(analytics_service, "_persist_signal", change_then_persist)

    with pytest.raises(AnalyticsConflict, match="Health data changed during analysis"):
        analytics_service.compute_trend(
            db_session,
            OWNER_ID,
            "energy",
            ANALYSIS_DATE,
            ANALYSIS_DATE,
            "America/Los_Angeles",
        )

    db_session.rollback()
    signal_count = db_session.scalar(
        select(func.count())
        .select_from(AnalyticsArtifact)
        .where(
            AnalyticsArtifact.owner_id == OWNER_ID,
            AnalyticsArtifact.artifact_kind == "derived_signal",
        )
    )
    assert signal_count == 0


@pytest.mark.asyncio
async def test_analytics_source_read_and_artifact_persistence_are_owner_scoped(
    analytics_client: AsyncClient,
    db_session: Session,
) -> None:
    event_id = uuid4()
    await _create_energy_event(analytics_client, event_id)
    db_session.add(
        User(
            id=OTHER_OWNER_ID,
            display_timezone="America/Los_Angeles",
            lifecycle="active",
            daily_sequence=0,
        )
    )
    db_session.commit()

    foreign_signal = analytics_service.compute_trend(
        db_session,
        OTHER_OWNER_ID,
        "energy",
        ANALYSIS_DATE,
        ANALYSIS_DATE,
        "America/Los_Angeles",
    )

    assert foreign_signal.obj.owner_id == OTHER_OWNER_ID
    assert foreign_signal.result.evidence_refs == []
    assert (
        db_session.scalar(
            select(AnalyticsEvidence).where(
                AnalyticsEvidence.owner_id == OTHER_OWNER_ID,
                AnalyticsEvidence.evidence_object_id == event_id,
            )
        )
        is None
    )
