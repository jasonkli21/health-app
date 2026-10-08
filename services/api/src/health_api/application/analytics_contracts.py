"""Typed records and shared errors for Health analytics application work."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from health_api.domain.analytics import (
    AssociationResult,
    DailyMetricPoint,
    EvidenceReference,
    MetricDefinition,
    TrendResult,
)
from health_api.domain.daily_rollups import DailyProvenance
from health_api.domain.schemas import EventSchemaV1, ObservationSchemaV1
from health_api.persistence.models import (
    AnalyticsArtifact,
    EventItem,
    HealthObject,
    ObservationItem,
)

type ArtifactAggregate = tuple[HealthObject, AnalyticsArtifact]
type EventInput = tuple[HealthObject, EventItem, EventSchemaV1]
type ObservationInput = tuple[HealthObject, ObservationItem, ObservationSchemaV1]
type MetricSeries = tuple[MetricDefinition, list[DailyMetricPoint], list[EvidenceReference], int]


class AnalyticsNotFound(Exception):
    """An owner-scoped analytics artifact or referenced resource is unavailable."""


class AnalyticsConflict(Exception):
    """An optimistic revision or lifecycle transition is stale or unsupported."""


class AnalyticsValidationError(Exception):
    """An analysis request or experiment violates the supported contract."""


@dataclass(frozen=True)
class AnalyticsSourceSnapshot:
    """Owner-scoped inputs and generation captured for one bounded calculation."""

    generation: int
    events: list[EventInput]
    observations: list[ObservationInput]
    links: dict[UUID, set[UUID]]
    provenance: dict[UUID, DailyProvenance]
    preferred_installations: dict[str, UUID]


@dataclass(frozen=True)
class StoredSignal:
    obj: HealthObject
    artifact: AnalyticsArtifact
    result: TrendResult | AssociationResult
    input_generation: int


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()
