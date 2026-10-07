"""Versioned, minimized contracts for optional read-only Personal AI access."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictBool, StrictInt, model_validator

from health_api.domain.analytics import AnalysisMetricId, TrendResult
from health_api.domain.daily_rollups import MetricSummaryV1
from health_api.domain.schemas import ConfirmationStatus, StrictModel

AIResourceType = Literal[
    "profile_item",
    "event",
    "observation",
    "goal",
    "regimen",
    "plan",
    "context",
]
AITaskKind = Literal[
    "general_wellness",
    "education",
    "understand_health_data",
    "consequential_medical",
    "urgent_safety",
]
AIContextSection = Literal["entries", "today_summaries", "trends"]


def _default_context_sections() -> list[AIContextSection]:
    return ["entries", "today_summaries"]


class AIContextRequest(StrictModel):
    task: Annotated[str, Field(min_length=1, max_length=300)]
    task_kind: AITaskKind = "general_wellness"
    resource_types: list[AIResourceType] = Field(min_length=1, max_length=7)
    as_of: AwareDatetime | None = None
    timezone: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    lookback_days: Annotated[StrictInt, Field(ge=0, le=90)] = 30
    excluded_object_ids: list[UUID] = Field(default_factory=list, max_length=100)
    domains: list[Annotated[str, Field(min_length=1, max_length=32)]] = Field(
        default_factory=list, max_length=16
    )
    sections: list[AIContextSection] = Field(
        default_factory=_default_context_sections, max_length=3
    )
    trend_metric: AnalysisMetricId | None = None

    @model_validator(mode="after")
    def validate_scope(self) -> AIContextRequest:
        if len(set(self.resource_types)) != len(self.resource_types):
            raise ValueError("resource_types must not contain duplicates")
        if len(set(self.excluded_object_ids)) != len(self.excluded_object_ids):
            raise ValueError("excluded_object_ids must not contain duplicates")
        if len(set(self.domains)) != len(self.domains) or len(set(self.sections)) != len(
            self.sections
        ):
            raise ValueError("domains and sections must not contain duplicates")
        if "entries" not in self.sections:
            raise ValueError("entries must be included in the request")
        if "trends" in self.sections:
            if self.trend_metric is None or not {"event", "observation"}.issubset(
                self.resource_types
            ):
                raise ValueError("trend context requires one metric and both daily resource types")
            if self.domains:
                raise ValueError("trend context requires the full supported domain scope")
        elif self.trend_metric is not None:
            raise ValueError("trend_metric requires the trends section")
        return self


class AIContextEntry(StrictModel):
    object_id: UUID
    revision: Annotated[StrictInt, Field(ge=1)]
    object_type: AIResourceType
    domain: Annotated[str, Field(min_length=1, max_length=32)]
    title: Annotated[str, Field(min_length=1, max_length=120)]
    valid_from: datetime | None
    valid_to: datetime | None
    source_kind: Literal["manual", "device", "document", "provider", "ai", "system"]
    confirmation_status: ConfirmationStatus
    content: dict[str, Any]
    content_is_user_data: Literal[True]
    relevance_reason: Annotated[str, Field(min_length=1, max_length=120)]


class AIContextPack(StrictModel):
    schema_version: Literal[1]
    request_id: UUID
    owner_scope: Annotated[str, Field(min_length=32, max_length=64)]
    built_at: AwareDatetime
    as_of: AwareDatetime
    timezone: Annotated[str, Field(min_length=1, max_length=64)]
    task: Annotated[str, Field(min_length=1, max_length=300)]
    task_kind: AITaskKind
    resource_types: list[AIResourceType]
    domains: list[str]
    sections: list[AIContextSection]
    lookback_days: Annotated[StrictInt, Field(ge=0, le=90)]
    entries: list[AIContextEntry] = Field(max_length=100)
    today_summary_date: date
    today_summary_scope: Literal["included_opted_in_entries_only"]
    today_summaries: list[MetricSummaryV1]
    trend_summary: TrendResult | None = None
    included_counts: dict[str, Annotated[StrictInt, Field(ge=0)]]
    omitted_by_user: Annotated[StrictInt, Field(ge=0)]
    omitted_by_budget: Annotated[StrictInt, Field(ge=0)]
    truncated: StrictBool
    budget_bytes: Literal[65536]
    serialized_bytes: Annotated[StrictInt, Field(ge=0, le=65536)]


class AISearchResult(StrictModel):
    object_id: UUID
    revision: Annotated[StrictInt, Field(ge=1)]
    object_type: AIResourceType
    domain: Annotated[str, Field(min_length=1, max_length=32)]
    title: Annotated[str, Field(min_length=1, max_length=120)]
    source_kind: Literal["manual", "device", "document", "provider", "ai", "system"]
    confirmation_status: ConfirmationStatus
    excerpt: Annotated[str, Field(max_length=400)]
    time_precision: Literal["instant", "date_only"] | None = None
    occurred_at: AwareDatetime | None = None
    local_date: date | None = None
    interval_end: AwareDatetime | None = None
    timezone: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    valid_from: AwareDatetime | None = None
    valid_to: AwareDatetime | None = None


class AISearchResponse(StrictModel):
    items: list[AISearchResult] = Field(max_length=50)
    next_cursor: str | None


class AssistantMessageRequest(StrictModel):
    message: Annotated[str, Field(min_length=1, max_length=8000)]
    scope: AIContextRequest


class AIEvidenceReference(StrictModel):
    object_id: UUID
    revision: Annotated[StrictInt, Field(ge=1)]
    object_type: AIResourceType | None = None
    title: Annotated[str, Field(min_length=1, max_length=120)] | None = None


class AssistantMessageResponse(StrictModel):
    request_id: UUID
    reply: Annotated[str, Field(max_length=8000)]
    risk_class: AITaskKind
    context_summary: dict[str, Annotated[StrictInt, Field(ge=0)]]
    evidence_refs: list[AIEvidenceReference] = Field(max_length=100)
    service_status: Literal["complete"]


class AssistantStatusResponse(StrictModel):
    enabled: StrictBool
    adapter_status: Literal["disabled", "ready"]
    allowed_capabilities: list[
        Literal[
            "health.context",
            "health.search",
            "health.today",
            "health.profile",
            "health.goals",
            "health.plans",
            "health.trends",
        ]
    ]
    message: Annotated[str, Field(max_length=240)]
