"""Bounded, versioned commands that require an explicit owner confirmation."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StrictInt, StrictStr, StringConstraints

from health_api.domain.planning import GoalPayloadV1, PlanPayloadV1, TrackerDefinitionV1
from health_api.domain.schemas import (
    EventSchemaV1,
    ObservationSchemaV1,
    ProfileMetadata,
    ProfileNotes,
    ProfilePayloadV1,
    StrictModel,
)

MAX_PROPOSAL_COMMANDS = 10
MAX_PROPOSAL_BYTES = 65_536
MAX_PROPOSAL_LIFETIME_HOURS = 24 * 7

ProposalRationale = Annotated[StrictStr, StringConstraints(max_length=1000)]
ProposalRejectReason = Annotated[StrictStr, StringConstraints(max_length=500)]
IdempotencyKey = Annotated[StrictStr, StringConstraints(min_length=1, max_length=128)]


class EvidenceReference(StrictModel):
    object_id: UUID
    revision: Annotated[StrictInt, Field(ge=1)]


class EvidenceDetail(EvidenceReference):
    object_type: str
    title: Annotated[StrictStr, StringConstraints(min_length=1, max_length=120)]


class ProfileCreateDraft(StrictModel):
    action: Literal["profile.create"]
    profile: ProfilePayloadV1
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    notes: ProfileNotes | None = None
    metadata: ProfileMetadata = Field(default_factory=ProfileMetadata)


class ProfileCreateCommand(ProfileCreateDraft):
    id: UUID


class ProfileUpdateCommand(StrictModel):
    action: Literal["profile.update"]
    object_id: UUID
    expected_revision: Annotated[StrictInt, Field(ge=1)]
    profile: ProfilePayloadV1
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    notes: ProfileNotes | None = None
    metadata: ProfileMetadata | None = None


class EventCreateDraft(StrictModel):
    action: Literal["event.create"]
    event: EventSchemaV1
    linked_observations: list[ObservationSchemaV1] = Field(default_factory=list, max_length=10)


class EventCreateCommand(EventCreateDraft):
    event_id: UUID
    observation_ids: list[UUID] = Field(default_factory=list, max_length=10)


class GoalCreateDraft(StrictModel):
    action: Literal["goal.create"]
    goal: GoalPayloadV1
    notes: Annotated[StrictStr, StringConstraints(max_length=2000)] | None = None


class GoalCreateCommand(GoalCreateDraft):
    id: UUID


class GoalUpdateCommand(StrictModel):
    action: Literal["goal.update"]
    object_id: UUID
    expected_revision: Annotated[StrictInt, Field(ge=1)]
    goal: GoalPayloadV1


class PlanCreateDraft(StrictModel):
    action: Literal["plan.create"]
    plan: PlanPayloadV1
    notes: Annotated[StrictStr, StringConstraints(max_length=2000)] | None = None


class PlanCreateCommand(PlanCreateDraft):
    id: UUID
    reference_revisions: list[EvidenceReference] = Field(default_factory=list, max_length=20)


class PlanUpdateCommand(StrictModel):
    action: Literal["plan.update"]
    object_id: UUID
    expected_revision: Annotated[StrictInt, Field(ge=1)]
    plan: PlanPayloadV1
    reference_revisions: list[EvidenceReference] = Field(default_factory=list, max_length=20)


class TrackerCreateDraft(StrictModel):
    action: Literal["tracker.create"]
    definition: TrackerDefinitionV1
    notes: Annotated[StrictStr, StringConstraints(max_length=2000)] | None = None


class TrackerCreateCommand(TrackerCreateDraft):
    id: UUID


type ProposalDraftCommand = Annotated[
    ProfileCreateDraft
    | ProfileUpdateCommand
    | EventCreateDraft
    | GoalCreateDraft
    | GoalUpdateCommand
    | PlanCreateDraft
    | PlanUpdateCommand
    | TrackerCreateDraft,
    Field(discriminator="action"),
]

type ProposalCommand = Annotated[
    ProfileCreateCommand
    | ProfileUpdateCommand
    | EventCreateCommand
    | GoalCreateCommand
    | GoalUpdateCommand
    | PlanCreateCommand
    | PlanUpdateCommand
    | TrackerCreateCommand,
    Field(discriminator="action"),
]


class ProposalContent(StrictModel):
    rationale: ProposalRationale = ""
    evidence_refs: list[EvidenceReference] = Field(default_factory=list, max_length=20)
    commands: list[ProposalDraftCommand] = Field(min_length=1, max_length=MAX_PROPOSAL_COMMANDS)


class StoredProposalContent(StrictModel):
    rationale: ProposalRationale = ""
    evidence_refs: list[EvidenceReference] = Field(default_factory=list, max_length=20)
    commands: list[ProposalCommand] = Field(min_length=1, max_length=MAX_PROPOSAL_COMMANDS)


class ProposalCreateRequest(ProposalContent):
    id: UUID


class ProposalEditRequest(ProposalContent):
    expected_revision: Annotated[StrictInt, Field(ge=1)]


class ProposalApplyRequest(StrictModel):
    proposal_revision: Annotated[StrictInt, Field(ge=1)]
    content_hash: Annotated[StrictStr, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    idempotency_key: IdempotencyKey
    confirmation: Literal["explicit_user_save"]


class ProposalRejectRequest(StrictModel):
    proposal_revision: Annotated[StrictInt, Field(ge=1)]
    reason: ProposalRejectReason | None = None


class ProposalResult(StrictModel):
    object_id: UUID
    object_type: Literal[
        "profile_item", "event", "observation", "goal", "plan", "tracker_definition"
    ]
    revision: Annotated[StrictInt, Field(ge=1)]


class ProposalChangeReview(StrictModel):
    object_id: UUID
    object_type: str
    title: str
    revision: Annotated[StrictInt, Field(ge=1)]
    before: dict[str, object] = Field(default_factory=dict)
    after: dict[str, object] = Field(default_factory=dict)
    preserved_fields: list[str] = Field(default_factory=list)
    cleared_fields: list[str] = Field(default_factory=list)
    removed_plan_items: list[dict[str, object]] = Field(default_factory=list)
    schedules_to_retire: Annotated[StrictInt, Field(ge=0)] = 0


class ProposalState(StrictModel):
    id: UUID
    revision: Annotated[StrictInt, Field(ge=1)]
    schema_version: Literal[1] = 1
    content_hash: Annotated[StrictStr, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    state: Literal["pending", "applied", "rejected", "expired", "superseded"]
    origin: Literal["user", "ai"]
    rationale: ProposalRationale
    evidence_refs: list[EvidenceDetail]
    commands: list[ProposalCommand]
    changes: list[ProposalChangeReview] = Field(default_factory=list)
    created_at: datetime
    expires_at: datetime
    updated_at: datetime
    last_validation_summary: dict[str, object] = Field(default_factory=dict)
    confirmed_by: UUID | None = None
    confirmed_at: datetime | None = None
    applied_at: datetime | None = None
    rejected_by: UUID | None = None
    rejected_at: datetime | None = None
    reject_reason: ProposalRejectReason | None = None
    results: list[ProposalResult] = Field(default_factory=list)


class ProposalSummary(StrictModel):
    id: UUID
    revision: Annotated[StrictInt, Field(ge=1)]
    content_hash: Annotated[StrictStr, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    state: Literal["pending", "applied", "rejected", "expired", "superseded"]
    origin: Literal["user", "ai"]
    rationale: ProposalRationale
    created_at: datetime
    expires_at: datetime
    updated_at: datetime


class ProposalListResponse(StrictModel):
    items: list[ProposalSummary]
    next_cursor: str | None


class ProposalHistoryEntry(StrictModel):
    event: Literal["created", "edited", "applied", "rejected", "expired"]
    proposal_revision: Annotated[StrictInt, Field(ge=1)]
    actor_id: UUID
    recorded_at: datetime
    details: dict[str, object] = Field(default_factory=dict)


class ProposalHistoryResponse(StrictModel):
    items: list[ProposalHistoryEntry]
    next_cursor: str | None = None


class ProposalApplyResponse(StrictModel):
    proposal: ProposalState
    replayed: bool = False
