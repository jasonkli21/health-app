"""Typed HTTP transport schemas for the Profile v1 API."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, ConfigDict, Field, StrictBool, StrictInt, model_validator

from health_api.domain.daily_rollups import MetricSummaryV1
from health_api.domain.planning import (
    ContextLifecycle,
    ContextPayloadV1,
    ContextRelation,
    ContextType,
    GoalLifecycle,
    GoalPayloadV1,
    PlanLifecycle,
    PlanPayloadV1,
    RegimenLifecycle,
    RegimenPayloadV1,
    ScheduleDefinitionV1,
    TrackerDefinitionV1,
)
from health_api.domain.schemas import (
    ConfirmationStatus,
    DailyDomain,
    DailyNotes,
    EventSchemaV1,
    ObservationSchemaV1,
    ProfileMetadata,
    ProfileNotes,
    ProfilePayloadV1,
    ProfileValidity,
    StrictModel,
)


def _non_null_openapi_schema(schema: dict[str, Any]) -> None:
    """The field may be omitted, but explicit JSON null is rejected by the model validator."""
    alternatives = schema.get("anyOf")
    if not isinstance(alternatives, list):
        return
    non_null = [alternative for alternative in alternatives if alternative.get("type") != "null"]
    if len(non_null) == 1:
        schema.pop("anyOf")
        schema.update(non_null[0])
    else:
        schema["anyOf"] = non_null


class ProfileCreateRequest(ProfileValidity):
    id: UUID
    profile: ProfilePayloadV1
    ai_use_allowed: StrictBool = False
    cross_domain_use_allowed: StrictBool = False
    notes: ProfileNotes | None = None
    metadata: ProfileMetadata = Field(default_factory=ProfileMetadata)


class ProfilePatchRequest(StrictModel):
    expected_revision: Annotated[StrictInt, Field(ge=1)]
    profile: ProfilePayloadV1 | None = Field(
        default=None,
        description="Omit to keep the current payload; explicit null is invalid.",
        json_schema_extra=_non_null_openapi_schema,
    )
    valid_from: AwareDatetime | None = None
    valid_to: AwareDatetime | None = None
    ai_use_allowed: StrictBool | None = Field(
        default=None, json_schema_extra=_non_null_openapi_schema
    )
    cross_domain_use_allowed: StrictBool | None = Field(
        default=None, json_schema_extra=_non_null_openapi_schema
    )
    notes: ProfileNotes | None = None
    metadata: ProfileMetadata | None = None

    @model_validator(mode="after")
    def reject_null_for_nonnullable_fields(self) -> ProfilePatchRequest:
        for name in (
            "profile",
            "ai_use_allowed",
            "cross_domain_use_allowed",
        ):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_from >= self.valid_to
        ):
            raise ValueError("valid_from must be earlier than valid_to")
        return self

    def changes(self) -> dict[str, object]:
        result: dict[str, object] = {}
        for name in self.model_fields_set - {"expected_revision"}:
            value = getattr(self, name)
            if name == "profile" and value is not None:
                result[name] = value.model_dump(mode="json")
            elif name == "metadata":
                result[name] = value.root if isinstance(value, ProfileMetadata) else {}
            else:
                result[name] = value
        return result


class ProfilePermissions(StrictModel):
    ai_use_allowed: StrictBool
    cross_domain_use_allowed: StrictBool


class ProfileSource(StrictModel):
    id: UUID
    kind: Literal["manual", "device", "document", "provider", "ai", "system"]
    name: Annotated[str, Field(min_length=1, max_length=120)]


class ProfileItemResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    object_type: Literal["profile_item"]
    domain: Literal["profile"]
    status: Literal["active", "archived"]
    title: Annotated[str, Field(min_length=1, max_length=120)]
    valid_from: datetime | None
    valid_to: datetime | None
    recorded_at: datetime
    created_at: datetime
    updated_at: datetime
    source: ProfileSource
    confirmation_status: ConfirmationStatus
    schema_version: Literal[1]
    revision: Annotated[int, Field(ge=1)]
    notes: ProfileNotes | None
    metadata: ProfileMetadata
    permissions: ProfilePermissions
    profile: ProfilePayloadV1


class ProfileListResponse(StrictModel):
    items: list[ProfileItemResponse]
    as_of: AwareDatetime
    next_cursor: str | None


class ProfileHistoryEntry(StrictModel):
    revision: Annotated[int, Field(ge=1)]
    recorded_at: datetime
    actor_kind: Literal["user"]
    reason: Literal["create", "update", "archive"]
    snapshot: ProfileItemResponse


class ProfileHistoryResponse(StrictModel):
    items: list[ProfileHistoryEntry]
    next_after_revision: int | None


class PlanningCreateRequestBase(StrictModel):
    id: UUID
    notes: DailyNotes | None = None
    ai_use_allowed: bool = False
    cross_domain_use_allowed: bool = False


class GoalCreateRequest(PlanningCreateRequestBase):
    goal: GoalPayloadV1


class RegimenCreateRequest(PlanningCreateRequestBase):
    regimen: RegimenPayloadV1


class PlanCreateRequest(PlanningCreateRequestBase):
    plan: PlanPayloadV1


class ContextCreateRequest(PlanningCreateRequestBase):
    context: ContextPayloadV1


class TrackerCreateRequest(PlanningCreateRequestBase):
    definition: TrackerDefinitionV1


class PlanningUpdateBase(StrictModel):
    expected_revision: Annotated[StrictInt, Field(ge=1)]
    ai_use_allowed: bool | None = None
    cross_domain_use_allowed: bool | None = None


class GoalUpdateRequest(PlanningUpdateBase):
    goal: GoalPayloadV1


class RegimenUpdateRequest(PlanningUpdateBase):
    regimen: RegimenPayloadV1


class PlanUpdateRequest(PlanningUpdateBase):
    plan: PlanPayloadV1


class PlanOrderRequest(PlanningUpdateBase):
    item_ids: list[UUID] = Field(min_length=0, max_length=50)


class ScheduleEditRequest(StrictModel):
    expected_schedule_revision: Annotated[StrictInt, Field(ge=1)] | None = None
    effective_from: date
    schedule: ScheduleDefinitionV1

    @model_validator(mode="after")
    def effective_date_is_representable(self) -> ScheduleEditRequest:
        if self.effective_from < date.min + timedelta(
            days=1
        ) or self.effective_from > date.max - timedelta(days=2):
            raise ValueError("effective_from is outside the supported calendar range")
        return self


class ScheduleResponse(StrictModel):
    schedule_id: UUID
    schedule_revision: Annotated[StrictInt, Field(ge=1)]
    effective_from: date
    schedule: ScheduleDefinitionV1


class OccurrenceActionRequest(StrictModel):
    expected_schedule_revision: Annotated[StrictInt, Field(ge=1)]
    expected_override_revision: Annotated[StrictInt, Field(ge=1)] | None = None
    state: Literal["completed", "skipped", "rescheduled"]
    rescheduled_at: AwareDatetime | None = None
    linked_event_id: UUID | None = None
    linked_observation_id: UUID | None = None

    @model_validator(mode="after")
    def reschedule_requires_new_due_time(self) -> OccurrenceActionRequest:
        if (self.state == "rescheduled") != (self.rescheduled_at is not None):
            raise ValueError("rescheduled_at is required only for a rescheduled occurrence")
        if self.linked_event_id is not None and self.linked_observation_id is not None:
            raise ValueError("link at most one existing Event or Observation")
        return self


class OccurrenceResponse(StrictModel):
    key: Annotated[str, Field(min_length=1, max_length=160)]
    parent_id: UUID
    item_id: UUID | None
    label: Annotated[str, Field(min_length=1, max_length=120)]
    schedule_id: UUID
    schedule_revision: Annotated[StrictInt, Field(ge=1)]
    original_local_date: date
    original_local_time: str
    timezone: Annotated[str, Field(min_length=1, max_length=64)]
    due_at: datetime
    dst_resolution: Literal["exact", "earlier_offset", "next_valid_time"]
    state: Literal["unknown", "completed", "skipped", "rescheduled"]
    can_act: bool = True
    override_revision: Annotated[StrictInt, Field(ge=1)] | None
    linked_event_id: UUID | None
    linked_observation_id: UUID | None = None


class OccurrenceListResponse(StrictModel):
    items: list[OccurrenceResponse]


class OccurrenceActionResponse(StrictModel):
    key: Annotated[str, Field(min_length=1, max_length=160)]
    state: Literal["completed", "skipped", "rescheduled"]
    override_revision: Annotated[StrictInt, Field(ge=1)]
    schedule_revision: Annotated[StrictInt, Field(ge=1)]
    rescheduled_at: datetime | None
    linked_event_id: UUID | None
    linked_observation_id: UUID | None = None
    updated_at: datetime


class OccurrenceHistoryEntry(StrictModel):
    revision: Annotated[StrictInt, Field(ge=1)]
    action: Literal["completed", "skipped", "rescheduled"]
    schedule_revision: Annotated[StrictInt, Field(ge=1)]
    acted_at: datetime
    rescheduled_at: datetime | None
    linked_event_id: UUID | None
    linked_observation_id: UUID | None


class OccurrenceHistoryResponse(StrictModel):
    items: list[OccurrenceHistoryEntry]
    next_after_revision: Annotated[StrictInt, Field(ge=1)] | None


class ContextUpdateRequest(PlanningUpdateBase):
    context: ContextPayloadV1


class TrackerUpdateRequest(PlanningUpdateBase):
    definition: TrackerDefinitionV1


class LifecycleUpdateRequest(PlanningUpdateBase):
    lifecycle: GoalLifecycle | RegimenLifecycle | PlanLifecycle | ContextLifecycle


class PlanningResourceResponseBase(StrictModel):
    id: UUID
    domain: str
    status: Literal["active", "archived"]
    title: Annotated[str, Field(min_length=1, max_length=120)]
    valid_from: datetime | None
    valid_to: datetime | None
    recorded_at: datetime
    created_at: datetime
    updated_at: datetime
    source: ProfileSource
    confirmation_status: ConfirmationStatus
    schema_version: Literal[1]
    revision: Annotated[int, Field(ge=1)]
    notes: DailyNotes | None
    ai_use_allowed: bool
    cross_domain_use_allowed: bool
    lifecycle: str


class GoalResponse(PlanningResourceResponseBase):
    object_type: Literal["goal"]
    goal: GoalPayloadV1


class RegimenResponse(PlanningResourceResponseBase):
    object_type: Literal["regimen"]
    regimen: RegimenPayloadV1


class PlanResponse(PlanningResourceResponseBase):
    object_type: Literal["plan"]
    plan: PlanPayloadV1


class ContextResponse(PlanningResourceResponseBase):
    object_type: Literal["context"]
    context: ContextPayloadV1


class TrackerResponse(PlanningResourceResponseBase):
    object_type: Literal["tracker_definition"]
    current_schema_version: Annotated[StrictInt, Field(ge=1)]
    definition: TrackerDefinitionV1


class TrackerSchemaVersionResponse(StrictModel):
    version: Annotated[StrictInt, Field(ge=1)]
    definition: TrackerDefinitionV1
    created_at: datetime


class TrackerSchemaVersionListResponse(StrictModel):
    items: list[TrackerSchemaVersionResponse]
    next_after_version: StrictInt | None


PlanningItemResponse = (
    GoalResponse | RegimenResponse | PlanResponse | ContextResponse | TrackerResponse
)


class PlanningListResponse(StrictModel):
    items: list[PlanningItemResponse]
    next_cursor: str | None


class PlanningHistoryEntry(StrictModel):
    revision: Annotated[StrictInt, Field(ge=1)]
    recorded_at: datetime
    actor_kind: Literal["user"]
    reason: Literal["create", "update", "archive"]
    snapshot: dict[str, Any]


class PlanningHistoryResponse(StrictModel):
    items: list[PlanningHistoryEntry]
    next_after_revision: int | None


class TodayContextSummary(StrictModel):
    id: UUID
    label: Annotated[str, Field(min_length=1, max_length=120)]
    context_type: ContextType
    notes: DailyNotes | None
    priority: Annotated[StrictInt, Field(ge=0, le=100)]
    related: list[ContextRelation]


class DailyEventCreateRequest(StrictModel):
    id: UUID
    event: EventSchemaV1
    ai_use_allowed: StrictBool = False


class DailyObservationCreateRequest(StrictModel):
    id: UUID
    observation: ObservationSchemaV1
    ai_use_allowed: StrictBool = False


class DailyLinkRequest(StrictModel):
    event_id: UUID
    observation_id: UUID
    role: Literal["symptom_severity"] = "symptom_severity"


class DailyEntryCreateRequest(StrictModel):
    events: list[DailyEventCreateRequest] = Field(default_factory=list, max_length=20)
    observations: list[DailyObservationCreateRequest] = Field(default_factory=list, max_length=20)
    links: list[DailyLinkRequest] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_atomic_entry_bounds(self) -> DailyEntryCreateRequest:
        objects = [item.id for item in self.events] + [item.id for item in self.observations]
        if not objects or len(objects) > 20:
            raise ValueError("daily entry must contain between one and twenty objects")
        if len(set(objects)) != len(objects):
            raise ValueError("daily entry object IDs must be unique")
        event_ids = {item.id for item in self.events}
        observation_ids = {item.id for item in self.observations}
        if any(
            link.event_id not in event_ids or link.observation_id not in observation_ids
            for link in self.links
        ):
            raise ValueError("linked objects must be included in the same atomic save")
        return self


class DailyEventUpdateRequest(StrictModel):
    expected_revision: Annotated[StrictInt, Field(ge=1)]
    event: EventSchemaV1
    ai_use_allowed: StrictBool | None = Field(
        default=None, json_schema_extra=_non_null_openapi_schema
    )

    @model_validator(mode="after")
    def permission_cannot_be_null(self) -> DailyEventUpdateRequest:
        if "ai_use_allowed" in self.model_fields_set and self.ai_use_allowed is None:
            raise ValueError("ai_use_allowed cannot be null")
        return self


class DailyObservationUpdateRequest(StrictModel):
    expected_revision: Annotated[StrictInt, Field(ge=1)]
    observation: ObservationSchemaV1
    ai_use_allowed: StrictBool | None = Field(
        default=None, json_schema_extra=_non_null_openapi_schema
    )

    @model_validator(mode="after")
    def permission_cannot_be_null(self) -> DailyObservationUpdateRequest:
        if "ai_use_allowed" in self.model_fields_set and self.ai_use_allowed is None:
            raise ValueError("ai_use_allowed cannot be null")
        return self


class DailyEnvelopeResponse(StrictModel):
    id: UUID
    domain: DailyDomain
    status: Literal["active", "archived"]
    title: Annotated[str, Field(min_length=1, max_length=120)]
    valid_from: datetime | None
    valid_to: datetime | None
    recorded_at: datetime
    created_at: datetime
    updated_at: datetime
    source: ProfileSource
    confirmation_status: ConfirmationStatus
    schema_version: Literal[1]
    revision: Annotated[int, Field(ge=1)]
    notes: DailyNotes | None
    metadata: ProfileMetadata
    permissions: ProfilePermissions


class DailyEventResponse(DailyEnvelopeResponse):
    object_type: Literal["event"]
    event: EventSchemaV1
    linked_observation_ids: list[UUID]


class DailyObservationResponse(DailyEnvelopeResponse):
    object_type: Literal["observation"]
    observation: ObservationSchemaV1


DailyItemResponse = Annotated[
    DailyEventResponse | DailyObservationResponse,
    Field(discriminator="object_type"),
]


class DailyEntryCreateResponse(StrictModel):
    events: list[DailyEventResponse]
    observations: list[DailyObservationResponse]
    created: bool


class DailyEventListResponse(StrictModel):
    items: list[DailyEventResponse]
    next_cursor: str | None


class DailyObservationListResponse(StrictModel):
    items: list[DailyObservationResponse]
    next_cursor: str | None


class DailyHistoryEntry(StrictModel):
    revision: Annotated[int, Field(ge=1)]
    recorded_at: datetime
    actor_kind: Literal["user"]
    reason: Literal["create", "update", "archive"]
    snapshot: DailyItemResponse


class DailyHistoryResponse(StrictModel):
    items: list[DailyHistoryEntry]
    next_after_revision: int | None


class ProfileContextReference(StrictModel):
    id: UUID
    title: Annotated[str, Field(min_length=1, max_length=120)]


class TodayResponse(StrictModel):
    date: date
    timezone: Annotated[str, Field(min_length=1, max_length=64)]
    as_of_sequence: Annotated[int, Field(ge=0)]
    items: list[DailyItemResponse]
    summaries: list[MetricSummaryV1]
    profile_context_refs: list[ProfileContextReference]
    profile_context_truncated: bool
    includes_profile_context: bool
    plan_items: list[OccurrenceResponse] = Field(default_factory=list)
    active_contexts: list[TodayContextSummary] = Field(default_factory=list)
    next_cursor: str | None


class FieldError(StrictModel):
    field: str
    message: str


class ErrorResponse(StrictModel):
    code: str
    message: str
    field_errors: list[FieldError] | None = None
    request_id: str
