"""PostgreSQL tables for the Phase 1 Profile vertical slice."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    cast,
    func,
    literal_column,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    display_timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    daily_sequence: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    __table_args__ = (
        CheckConstraint("lifecycle IN ('active', 'disabled')", name="ck_users_lifecycle"),
        CheckConstraint("daily_sequence >= 0", name="ck_users_daily_sequence"),
    )


class ActionProposal(Base):
    """Current lifecycle pointer for an immutable owner-scoped proposal stream."""

    __tablename__ = "action_proposals"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    schema_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    state: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    origin_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    origin_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    current_revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_revision: Mapped[int | None] = mapped_column(Integer)
    rejected_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reject_reason: Mapped[str | None] = mapped_column(String(500))
    result_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    last_validation_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    __table_args__ = (
        UniqueConstraint("owner_id", "id", name="uq_action_proposals_owner_id"),
        ForeignKeyConstraint(
            ["owner_id"], ["users.id"], ondelete="CASCADE", name="fk_action_proposals_owner"
        ),
        CheckConstraint("schema_version = 1", name="ck_action_proposals_schema_version"),
        CheckConstraint(
            "state IN ('pending', 'applied', 'rejected', 'expired', 'superseded')",
            name="ck_action_proposals_state",
        ),
        CheckConstraint("origin_kind IN ('user', 'ai')", name="ck_action_proposals_origin"),
        CheckConstraint("current_revision > 0", name="ck_action_proposals_revision"),
        CheckConstraint("length(content_hash) = 64", name="ck_action_proposals_hash"),
        CheckConstraint(
            "expires_at > created_at AND expires_at <= created_at + interval '7 days'",
            name="ck_action_proposals_expiry",
        ),
        CheckConstraint(
            "(confirmed_by IS NULL) = (confirmed_at IS NULL)",
            name="ck_action_proposals_confirmation_pair",
        ),
        CheckConstraint(
            "(rejected_by IS NULL) = (rejected_at IS NULL)",
            name="ck_action_proposals_rejection_pair",
        ),
        CheckConstraint(
            "state <> 'applied' OR (confirmed_by = owner_id AND applied_at IS NOT NULL AND applied_revision IS NOT NULL AND result_json IS NOT NULL)",
            name="ck_action_proposals_applied_result",
        ),
        Index("ix_action_proposals_owner_state_created", "owner_id", "state", "created_at", "id"),
    )


class ActionProposalRevision(Base):
    """Immutable typed command and evidence snapshot for one proposal revision."""

    __tablename__ = "action_proposal_revisions"

    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    proposal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    schema_version: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    actor_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "proposal_id"],
            ["action_proposals.owner_id", "action_proposals.id"],
            ondelete="CASCADE",
            name="fk_action_proposal_revisions_owner_proposal",
        ),
        CheckConstraint("revision > 0", name="ck_action_proposal_revisions_revision"),
        CheckConstraint("schema_version = 1", name="ck_action_proposal_revisions_schema_version"),
        CheckConstraint("length(content_hash) = 64", name="ck_action_proposal_revisions_hash"),
        CheckConstraint("actor_id = owner_id", name="ck_action_proposal_revisions_actor"),
    )


class ActionProposalEvent(Base):
    """Append-only owner-visible lifecycle and confirmation audit entry."""

    __tablename__ = "action_proposal_events"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    proposal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    proposal_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    event: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "proposal_id", "proposal_revision"],
            [
                "action_proposal_revisions.owner_id",
                "action_proposal_revisions.proposal_id",
                "action_proposal_revisions.revision",
            ],
            ondelete="CASCADE",
            name="fk_action_proposal_events_revision",
        ),
        CheckConstraint("proposal_revision > 0", name="ck_action_proposal_events_revision"),
        CheckConstraint(
            "event IN ('created', 'edited', 'applied', 'rejected', 'expired')",
            name="ck_action_proposal_events_event",
        ),
        CheckConstraint("actor_id = owner_id", name="ck_action_proposal_events_actor"),
        Index(
            "ix_action_proposal_events_owner_proposal_recorded",
            "owner_id",
            "proposal_id",
            "recorded_at",
            "id",
        ),
    )


class ActionCommandReceipt(Base):
    """Durable replay protection committed with the approved health changes."""

    __tablename__ = "action_command_receipts"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    proposal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    proposal_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "proposal_id", "proposal_revision"],
            [
                "action_proposal_revisions.owner_id",
                "action_proposal_revisions.proposal_id",
                "action_proposal_revisions.revision",
            ],
            ondelete="RESTRICT",
            name="fk_action_command_receipts_revision",
        ),
        UniqueConstraint(
            "owner_id", "idempotency_key", name="uq_action_command_receipts_owner_key"
        ),
        CheckConstraint("proposal_revision > 0", name="ck_action_command_receipts_revision"),
        CheckConstraint(
            "length(idempotency_key) BETWEEN 1 AND 128", name="ck_action_command_receipts_key"
        ),
        CheckConstraint("length(content_hash) = 64", name="ck_action_command_receipts_hash"),
    )


class ProviderIdentity(Base):
    """A verified external subject mapped to one stable internal owner UUID."""

    __tablename__ = "provider_identities"

    issuer: Mapped[str] = mapped_column(String(256), primary_key=True)
    subject: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_provider_identities_user"),
        CheckConstraint(
            "char_length(issuer) BETWEEN 1 AND 256", name="ck_provider_identity_issuer"
        ),
        CheckConstraint(
            "char_length(subject) BETWEEN 1 AND 128", name="ck_provider_identity_subject"
        ),
    )


class DailySnapshotMarker(Base):
    """Sequences that may safely anchor a complete committed Today snapshot."""

    __tablename__ = "daily_snapshot_markers"

    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    daily_sequence: Mapped[int] = mapped_column(Integer, primary_key=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id"], ["users.id"], ondelete="CASCADE", name="fk_daily_snapshot_markers_owner"
        ),
        CheckConstraint("daily_sequence >= 0", name="ck_daily_snapshot_markers_sequence"),
    )


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source_key: Mapped[str] = mapped_column(String(64), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    external_namespace: Mapped[str | None] = mapped_column(String(120))
    external_identifier: Mapped[str | None] = mapped_column(String(256))
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("owner_id", "id", name="uq_sources_owner_id"),
        UniqueConstraint("owner_id", "source_key", name="uq_sources_owner_key"),
        CheckConstraint(
            "source_kind IN ('manual', 'device', 'document', 'provider', 'ai', 'system')",
            name="ck_sources_kind",
        ),
        CheckConstraint(
            "(external_namespace IS NULL) = (external_identifier IS NULL)",
            name="ck_sources_external_identity_pair",
        ),
    )


class HealthKitImportBatch(Base):
    """Idempotent owner-scoped receipt for one bounded HealthKit upload."""

    __tablename__ = "healthkit_import_batches"

    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    batch_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    device_installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    unchanged_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    tombstoned_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    correction_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    conflict_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id"], ["users.id"], ondelete="CASCADE", name="fk_healthkit_batches_owner"
        ),
        CheckConstraint(
            "resource_type IN ('workouts', 'sleep', 'steps', 'weight', "
            "'resting_heart_rate', 'heart_rate_summary')",
            name="ck_healthkit_batches_resource_type",
        ),
        CheckConstraint("policy_version = 'healthkit-v1'", name="ck_healthkit_batches_policy"),
        CheckConstraint("length(content_hash) = 64", name="ck_healthkit_batches_hash"),
        CheckConstraint(
            "created_count >= 0 AND updated_count >= 0 AND unchanged_count >= 0 AND "
            "tombstoned_count >= 0 AND correction_count >= 0 AND conflict_count >= 0",
            name="ck_healthkit_batches_counts",
        ),
        Index("ix_healthkit_batches_owner_created", "owner_id", "created_at"),
    )


class HealthKitImportIdentity(Base):
    """Maps a HealthKit source identity to its current canonical daily object."""

    __tablename__ = "healthkit_import_identities"

    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    platform: Mapped[str] = mapped_column(
        String(24), primary_key=True, server_default="apple_healthkit"
    )
    resource_type: Mapped[str] = mapped_column(String(32), primary_key=True)
    source_sample_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    device_installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_aggregate: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    aggregate_date: Mapped[date | None] = mapped_column(Date)
    aggregate_timezone: Mapped[str | None] = mapped_column(String(64))
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    analytics_selected: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    tombstoned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id"], ["users.id"], ondelete="CASCADE", name="fk_healthkit_identity_owner"
        ),
        ForeignKeyConstraint(
            ["owner_id", "object_id"],
            ["health_objects.owner_id", "health_objects.id"],
            ondelete="CASCADE",
            name="fk_healthkit_identity_object",
        ),
        CheckConstraint("platform = 'apple_healthkit'", name="ck_healthkit_identity_platform"),
        CheckConstraint(
            "resource_type IN ('workouts', 'sleep', 'steps', 'weight', "
            "'resting_heart_rate', 'heart_rate_summary')",
            name="ck_healthkit_identity_resource_type",
        ),
        CheckConstraint("length(content_hash) = 64", name="ck_healthkit_identity_hash"),
        CheckConstraint("policy_version = 'healthkit-v1'", name="ck_healthkit_identity_policy"),
        CheckConstraint(
            "(is_aggregate AND aggregate_date IS NOT NULL AND aggregate_timezone IS NOT NULL) OR "
            "(NOT is_aggregate AND aggregate_date IS NULL AND aggregate_timezone IS NULL AND analytics_selected)",
            name="ck_healthkit_identity_aggregate_shape",
        ),
        UniqueConstraint("owner_id", "object_id", name="uq_healthkit_identity_object"),
        Index(
            "ix_healthkit_identity_owner_aggregate",
            "owner_id",
            "resource_type",
            "aggregate_date",
            "analytics_selected",
        ),
    )


class HealthKitSourcePreference(Base):
    """Owner-authored source choice for device-day aggregate inputs."""

    __tablename__ = "healthkit_source_preferences"

    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    resource_type: Mapped[str] = mapped_column(String(32), primary_key=True)
    device_installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    source_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id"], ["users.id"], ondelete="CASCADE", name="fk_healthkit_preferences_owner"
        ),
        ForeignKeyConstraint(
            ["owner_id", "source_id"],
            ["sources.owner_id", "sources.id"],
            ondelete="RESTRICT",
            name="fk_healthkit_preferences_source",
        ),
        CheckConstraint(
            "resource_type IN ('steps', 'heart_rate_summary')",
            name="ck_healthkit_preferences_resource_type",
        ),
        CheckConstraint("revision > 0", name="ck_healthkit_preferences_revision"),
    )


class HealthObject(Base):
    __tablename__ = "health_objects"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    object_type: Mapped[str] = mapped_column(String(32), nullable=False)
    domain: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    source_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    confirmation_status: Mapped[str] = mapped_column(String(24), nullable=False)
    schema_version: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    notes: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    ai_use_allowed: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    cross_domain_use_allowed: Mapped[bool] = mapped_column(
        nullable=False, server_default=text("false")
    )
    create_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)

    profile_item: Mapped[ProfileItem] = relationship(
        back_populates="health_object", uselist=False, cascade="all, delete-orphan"
    )
    event_item: Mapped[EventItem | None] = relationship(
        back_populates="health_object", uselist=False, cascade="all, delete-orphan"
    )
    analytics_artifact: Mapped[AnalyticsArtifact | None] = relationship(
        back_populates="health_object", uselist=False, cascade="all, delete-orphan"
    )
    observation_item: Mapped[ObservationItem | None] = relationship(
        back_populates="health_object",
        uselist=False,
        cascade="all, delete-orphan",
        foreign_keys="[ObservationItem.owner_id, ObservationItem.object_id]",
    )
    planning_resource: Mapped[PlanningResource | None] = relationship(
        back_populates="health_object", uselist=False, cascade="all, delete-orphan"
    )
    revisions: Mapped[list[HealthObjectRevision]] = relationship(
        back_populates="health_object", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("owner_id", "id", name="uq_health_objects_owner_id"),
        ForeignKeyConstraint(
            ["owner_id", "source_id"],
            ["sources.owner_id", "sources.id"],
            ondelete="RESTRICT",
            name="fk_health_objects_owner_source",
        ),
        CheckConstraint(
            "object_type IN ('profile_item', 'event', 'observation', 'goal', 'regimen', 'plan', "
            "'context', 'tracker_definition', 'derived_signal', 'insight', 'recommendation', 'experiment')",
            name="ck_health_objects_type",
        ),
        CheckConstraint(
            "(object_type = 'profile_item' AND domain = 'profile') OR "
            "(object_type = 'event' AND domain IN ('nutrition', 'exercise', 'sleep', 'symptoms')) OR "
            "(object_type = 'observation' AND domain IN ('measurements', 'symptoms', 'nutrition', 'exercise', 'sleep')) OR "
            "(object_type IN ('goal', 'regimen', 'plan', 'context', 'tracker_definition') AND domain IN "
            "('planning', 'nutrition', 'exercise', 'sleep', 'symptoms', 'measurements', 'general')) OR "
            "(object_type IN ('derived_signal', 'insight', 'recommendation', 'experiment') AND domain = 'analytics')",
            name="ck_health_objects_domain_type",
        ),
        CheckConstraint("status IN ('active', 'archived')", name="ck_health_objects_status"),
        CheckConstraint(
            "confirmation_status IN ('unconfirmed', 'user_confirmed')",
            name="ck_health_objects_confirmation",
        ),
        CheckConstraint("schema_version = 1", name="ck_health_objects_schema_version"),
        CheckConstraint("revision > 0", name="ck_health_objects_revision"),
        CheckConstraint(
            "notes IS NULL OR char_length(notes) <= 4000", name="ck_health_objects_notes"
        ),
        CheckConstraint(
            "valid_from IS NULL OR valid_to IS NULL OR valid_from < valid_to",
            name="ck_health_objects_validity",
        ),
        Index("ix_health_objects_owner_status_created", "owner_id", "status", "created_at", "id"),
        Index(
            "ix_health_objects_ai_search",
            func.to_tsvector(
                literal_column("'simple'"),
                func.coalesce(title, literal_column("''"))
                .op("||")(literal_column("' '"))
                .op("||")(func.coalesce(notes, literal_column("''"))),
            ),
            postgresql_using="gin",
        ),
    )


class ProfileItem(Base):
    __tablename__ = "profile_items"

    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    category: Mapped[str] = mapped_column(String(24), nullable=False)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    health_object: Mapped[HealthObject] = relationship(back_populates="profile_item")

    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "object_id"],
            ["health_objects.owner_id", "health_objects.id"],
            ondelete="CASCADE",
            name="fk_profile_items_owner_object",
        ),
        CheckConstraint(
            "(kind = 'fact' AND category = 'background') OR "
            "(kind = 'constraint' AND category = 'constraints') OR "
            "(kind = 'preference' AND category = 'preferences')",
            name="ck_profile_items_kind_category",
        ),
        CheckConstraint("key ~ '^[a-z][a-z0-9_]{0,63}$'", name="ck_profile_items_key"),
        CheckConstraint(
            "jsonb_typeof(payload) = 'object' AND "
            "payload ? 'kind' AND jsonb_typeof(payload->'kind') = 'string' AND "
            "payload->>'kind' = kind AND payload ? 'category' AND "
            "jsonb_typeof(payload->'category') = 'string' AND "
            "payload->>'category' = category AND payload ? 'key' AND "
            "jsonb_typeof(payload->'key') = 'string' AND payload->>'key' = key",
            name="ck_profile_items_payload_consistency",
        ),
        Index("ix_profile_items_owner_category_key", "owner_id", "category", "key"),
        Index(
            "ix_profile_items_ai_search",
            func.to_tsvector(
                literal_column("'simple'"),
                cast(
                    payload.op("-")("related").op("-")("items").op("-")("linked_observation_ids"),
                    Text,
                ),
            ),
            postgresql_using="gin",
        ),
    )


class HealthObjectRevision(Base):
    __tablename__ = "health_object_revisions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    proposal_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actor_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(16), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    daily_sequence: Mapped[int | None] = mapped_column(Integer)
    daily_object_type: Mapped[str | None] = mapped_column(String(16))
    daily_domain: Mapped[str | None] = mapped_column(String(24))
    daily_status: Mapped[str | None] = mapped_column(String(16))
    daily_time_precision: Mapped[str | None] = mapped_column(String(16))
    daily_occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    daily_local_date: Mapped[date | None] = mapped_column(Date)
    daily_ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    health_object: Mapped[HealthObject] = relationship(back_populates="revisions")

    __table_args__ = (
        UniqueConstraint("owner_id", "object_id", "revision", name="uq_health_object_revision"),
        ForeignKeyConstraint(
            ["owner_id", "object_id"],
            ["health_objects.owner_id", "health_objects.id"],
            ondelete="CASCADE",
            name="fk_health_object_revisions_owner_object",
        ),
        ForeignKeyConstraint(
            ["owner_id", "proposal_id"],
            ["action_proposals.owner_id", "action_proposals.id"],
            ondelete="RESTRICT",
            name="fk_health_object_revisions_owner_proposal",
        ),
        CheckConstraint("actor_id = owner_id", name="ck_health_object_revisions_owner_actor"),
        CheckConstraint("revision > 0", name="ck_health_object_revisions_revision"),
        CheckConstraint("actor_kind = 'user'", name="ck_health_object_revisions_actor_kind"),
        CheckConstraint(
            "reason IN ('create', 'update', 'archive')", name="ck_health_object_revisions_reason"
        ),
        CheckConstraint(
            "(daily_sequence IS NULL AND daily_object_type IS NULL AND daily_domain IS NULL AND "
            "daily_status IS NULL AND daily_time_precision IS NULL AND daily_occurred_at IS NULL AND "
            "daily_local_date IS NULL AND daily_ended_at IS NULL) OR "
            "(daily_sequence > 0 AND daily_object_type IN ('event', 'observation') AND "
            "daily_domain IN ('nutrition', 'exercise', 'sleep', 'symptoms', 'measurements') AND "
            "daily_status IN ('active', 'archived') AND "
            "((daily_time_precision = 'instant' AND daily_occurred_at IS NOT NULL AND "
            "daily_local_date IS NULL) OR (daily_time_precision = 'date_only' AND "
            "daily_occurred_at IS NULL AND daily_local_date IS NOT NULL AND daily_ended_at IS NULL)))",
            name="ck_health_object_revisions_daily_snapshot_shape",
        ),
        Index(
            "ix_health_revisions_owner_daily_instant",
            "owner_id",
            "daily_domain",
            "daily_occurred_at",
            "object_id",
            "daily_sequence",
        ),
        Index(
            "ix_health_revisions_owner_daily_date",
            "owner_id",
            "daily_domain",
            "daily_local_date",
            "object_id",
            "daily_sequence",
        ),
        Index(
            "ix_health_revisions_owner_object_daily_sequence",
            "owner_id",
            "object_id",
            "daily_sequence",
        ),
    )


class EventItem(Base):
    __tablename__ = "events"

    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    event_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    time_precision: Mapped[str] = mapped_column(String(16), nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    local_date: Mapped[date | None] = mapped_column(Date)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    health_object: Mapped[HealthObject] = relationship(back_populates="event_item")

    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "object_id"],
            ["health_objects.owner_id", "health_objects.id"],
            ondelete="CASCADE",
            name="fk_events_owner_object",
        ),
        CheckConstraint(
            "event_kind IN ('meal', 'workout', 'sleep', 'symptom')", name="ck_events_kind"
        ),
        CheckConstraint(
            "(time_precision = 'instant' AND occurred_at IS NOT NULL AND local_date IS NULL) OR "
            "(time_precision = 'date_only' AND occurred_at IS NULL AND local_date IS NOT NULL AND ended_at IS NULL)",
            name="ck_events_time_precision_shape",
        ),
        CheckConstraint(
            "ended_at IS NULL OR (occurred_at IS NOT NULL AND occurred_at < ended_at)",
            name="ck_events_interval",
        ),
        CheckConstraint("char_length(timezone) BETWEEN 1 AND 64", name="ck_events_timezone_length"),
        CheckConstraint(
            "jsonb_typeof(payload) = 'object' AND payload ? 'kind' AND "
            "jsonb_typeof(payload->'kind') = 'string' AND payload->>'kind' = event_kind",
            name="ck_events_payload_kind",
        ),
        Index("ix_events_owner_instant", "owner_id", "occurred_at", "object_id"),
        Index("ix_events_owner_date", "owner_id", "local_date", "object_id"),
        Index(
            "ix_events_ai_search",
            func.to_tsvector(
                literal_column("'simple'"),
                cast(
                    payload.op("-")("related").op("-")("items").op("-")("linked_observation_ids"),
                    Text,
                ),
            ),
            postgresql_using="gin",
        ),
    )


class ObservationItem(Base):
    __tablename__ = "observations"

    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    metric_key: Mapped[str] = mapped_column(String(32), nullable=False)
    time_precision: Mapped[str] = mapped_column(String(16), nullable=False)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    local_date: Mapped[date | None] = mapped_column(Date)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    interval_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    numeric_value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    tracker_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    tracker_schema_version: Mapped[int | None] = mapped_column(SmallInteger)
    # `None` means no custom tracker payload. Bind it as SQL NULL so ordinary
    # observations satisfy the tracker-shape constraint instead of storing JSON null.
    tracker_values: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))

    health_object: Mapped[HealthObject] = relationship(
        back_populates="observation_item",
        foreign_keys=[owner_id, object_id],
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "object_id"],
            ["health_objects.owner_id", "health_objects.id"],
            ondelete="CASCADE",
            name="fk_observations_owner_object",
        ),
        CheckConstraint(
            "metric_key IN ('weight', 'temperature', 'systolic_pressure', "
            "'diastolic_pressure', 'pulse', 'steps', 'resting_heart_rate', "
            "'heart_rate_summary', 'symptom_severity', 'custom')",
            name="ck_observations_metric",
        ),
        CheckConstraint(
            "(metric_key = 'weight' AND unit IN ('kg', 'lb')) OR "
            "(metric_key = 'temperature' AND unit IN ('C', 'F')) OR "
            "(metric_key IN ('systolic_pressure', 'diastolic_pressure') AND unit = 'mmHg') OR "
            "(metric_key IN ('pulse', 'resting_heart_rate', 'heart_rate_summary') AND unit = 'bpm') OR "
            "(metric_key = 'steps' AND unit = 'steps') OR "
            "(metric_key = 'symptom_severity' AND unit = 'score') OR "
            "(metric_key = 'custom' AND unit = 'custom')",
            name="ck_observations_metric_unit",
        ),
        CheckConstraint(
            "(metric_key = 'custom' AND numeric_value IS NULL) OR "
            "(metric_key <> 'custom' AND numeric_value IS NOT NULL AND "
            "numeric_value > '-Infinity'::double precision AND "
            "numeric_value < 'Infinity'::double precision AND "
            "(metric_key <> 'symptom_severity' OR "
            "(numeric_value >= 0 AND numeric_value <= 10 AND numeric_value = trunc(numeric_value))))",
            name="ck_observations_numeric_value",
        ),
        CheckConstraint(
            "(time_precision = 'instant' AND observed_at IS NOT NULL AND local_date IS NULL) OR "
            "(time_precision = 'date_only' AND observed_at IS NULL AND local_date IS NOT NULL AND interval_end IS NULL)",
            name="ck_observations_time_precision_shape",
        ),
        CheckConstraint(
            "interval_end IS NULL OR (observed_at IS NOT NULL AND observed_at < interval_end)",
            name="ck_observations_interval",
        ),
        CheckConstraint(
            "char_length(timezone) BETWEEN 1 AND 64", name="ck_observations_timezone_length"
        ),
        CheckConstraint(
            "(metric_key = 'custom' AND jsonb_typeof(payload) = 'object' AND "
            "payload ? 'value' AND jsonb_typeof(payload->'value') = 'object' AND "
            "payload->'value'->>'metric' = 'custom' AND payload->'value'->>'unit' = 'custom') OR "
            "(metric_key <> 'custom' AND jsonb_typeof(payload) = 'object' AND payload ? 'value' AND "
            "jsonb_typeof(payload->'value') = 'object' AND "
            "payload->'value' ? 'metric' AND "
            "jsonb_typeof(payload->'value'->'metric') = 'string' AND "
            "payload->'value'->>'metric' = metric_key AND "
            "payload->'value' ? 'unit' AND "
            "jsonb_typeof(payload->'value'->'unit') = 'string' AND "
            "payload->'value'->>'unit' = unit AND "
            "payload->'value' ? 'value' AND "
            "jsonb_typeof(payload->'value'->'value') = 'number' AND "
            "(payload->'value'->>'value')::double precision = numeric_value)",
            name="ck_observations_payload_consistency",
        ),
        ForeignKeyConstraint(
            ["owner_id", "tracker_id"],
            ["health_objects.owner_id", "health_objects.id"],
            ondelete="RESTRICT",
            name="fk_observations_owner_tracker",
        ),
        CheckConstraint(
            "(metric_key = 'custom' AND tracker_id IS NOT NULL AND "
            "tracker_schema_version IS NOT NULL AND tracker_schema_version > 0 AND "
            "jsonb_typeof(tracker_values) = 'object') OR "
            "(metric_key <> 'custom' AND tracker_id IS NULL AND "
            "tracker_schema_version IS NULL AND tracker_values IS NULL)",
            name="ck_observations_tracker_shape",
        ),
        Index(
            "ix_observations_owner_metric_instant",
            "owner_id",
            "metric_key",
            "observed_at",
            "object_id",
        ),
        Index(
            "ix_observations_owner_metric_date", "owner_id", "metric_key", "local_date", "object_id"
        ),
        Index(
            "ix_observations_ai_search",
            func.to_tsvector(
                literal_column("'simple'"),
                cast(
                    payload.op("-")("related").op("-")("items").op("-")("linked_observation_ids"),
                    Text,
                ),
            ),
            postgresql_using="gin",
        ),
    )


class EventObservationLink(Base):
    __tablename__ = "event_observation_links"

    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    event_object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    observation_object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "event_object_id"],
            ["events.owner_id", "events.object_id"],
            ondelete="CASCADE",
            name="fk_event_observation_links_owner_event",
        ),
        ForeignKeyConstraint(
            ["owner_id", "observation_object_id"],
            ["observations.owner_id", "observations.object_id"],
            ondelete="CASCADE",
            name="fk_event_observation_links_owner_observation",
        ),
        CheckConstraint("role = 'symptom_severity'", name="ck_event_observation_links_role"),
        UniqueConstraint(
            "owner_id", "event_object_id", "role", name="uq_event_observation_link_role"
        ),
        UniqueConstraint(
            "owner_id", "observation_object_id", "role", name="uq_observation_event_link_role"
        ),
        Index("ix_event_observation_links_owner_observation", "owner_id", "observation_object_id"),
    )


class PlanningResource(Base):
    """Typed planning subtype payload attached to a canonical HealthObject."""

    __tablename__ = "planning_resources"

    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    resource_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(16), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    current_schema_version: Mapped[int | None] = mapped_column(SmallInteger)

    health_object: Mapped[HealthObject] = relationship(back_populates="planning_resource")

    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "object_id"],
            ["health_objects.owner_id", "health_objects.id"],
            ondelete="CASCADE",
            name="fk_planning_resources_owner_object",
        ),
        CheckConstraint(
            "resource_kind IN ('goal', 'regimen', 'plan', 'context', 'tracker_definition')",
            name="ck_planning_resources_kind",
        ),
        CheckConstraint(
            "lifecycle IN ('active', 'paused', 'completed', 'ended')",
            name="ck_planning_resources_lifecycle",
        ),
        CheckConstraint(
            "(resource_kind = 'goal' AND lifecycle IN ('active', 'paused', 'completed')) OR "
            "(resource_kind = 'regimen' AND lifecycle IN ('active', 'paused', 'completed')) OR "
            "(resource_kind = 'plan' AND lifecycle IN ('active', 'paused', 'completed')) OR "
            "(resource_kind = 'context' AND lifecycle IN ('active', 'ended')) OR "
            "(resource_kind = 'tracker_definition' AND lifecycle = 'active')",
            name="ck_planning_resources_kind_lifecycle",
        ),
        CheckConstraint(
            "(resource_kind = 'tracker_definition' AND current_schema_version > 0) OR "
            "(resource_kind <> 'tracker_definition' AND current_schema_version IS NULL)",
            name="ck_planning_resources_tracker_version",
        ),
        CheckConstraint("jsonb_typeof(payload) = 'object'", name="ck_planning_resources_payload"),
        Index(
            "ix_planning_resources_owner_kind_lifecycle", "owner_id", "resource_kind", "lifecycle"
        ),
        Index(
            "ix_planning_resources_ai_search",
            func.to_tsvector(
                literal_column("'simple'"),
                cast(
                    payload.op("-")("related").op("-")("items").op("-")("linked_observation_ids"),
                    Text,
                ),
            ),
            postgresql_using="gin",
        ),
    )


class AnalyticsArtifact(Base):
    """Versioned analytical snapshot attached to a canonical HealthObject."""

    __tablename__ = "analytics_artifacts"

    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    artifact_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_key: Mapped[str | None] = mapped_column(String(128))
    dedupe_key: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    health_object: Mapped[HealthObject] = relationship(back_populates="analytics_artifact")

    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "object_id"],
            ["health_objects.owner_id", "health_objects.id"],
            ondelete="CASCADE",
            name="fk_analytics_artifacts_owner_object",
        ),
        CheckConstraint(
            "artifact_kind IN ('derived_signal', 'insight', 'recommendation', 'experiment')",
            name="ck_analytics_artifacts_kind",
        ),
        CheckConstraint(
            "(artifact_kind = 'derived_signal' AND state IN ('current', 'stale')) OR "
            "(artifact_kind = 'insight' AND state IN ('current', 'stale', 'dismissed', 'expired')) OR "
            "(artifact_kind = 'recommendation' AND state IN ('proposed', 'accepted', 'dismissed', 'expired', 'stale')) OR "
            "(artifact_kind = 'experiment' AND state IN ('draft', 'active', 'completed', 'stopped', 'archived'))",
            name="ck_analytics_artifacts_state",
        ),
        CheckConstraint(
            "(dedupe_key IS NULL OR length(dedupe_key) = 64)",
            name="ck_analytics_artifacts_dedupe_key",
        ),
        CheckConstraint(
            "artifact_kind = 'derived_signal' OR scope_key IS NULL",
            name="ck_analytics_artifacts_scope_key",
        ),
        UniqueConstraint(
            "owner_id", "artifact_kind", "dedupe_key", name="uq_analytics_artifacts_dedupe"
        ),
        Index(
            "ix_analytics_artifacts_owner_kind_state_updated",
            "owner_id",
            "artifact_kind",
            "state",
            "updated_at",
            "object_id",
        ),
        Index(
            "ix_analytics_artifacts_owner_kind_scope_state",
            "owner_id",
            "artifact_kind",
            "scope_key",
            "state",
        ),
    )


class AnalyticsEvidence(Base):
    """Exact owner-scoped source revisions used by one analytical snapshot."""

    __tablename__ = "analytics_evidence"

    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    artifact_object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    evidence_object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    evidence_revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    evidence_object_type: Mapped[str] = mapped_column(String(16), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "artifact_object_id"],
            ["analytics_artifacts.owner_id", "analytics_artifacts.object_id"],
            ondelete="CASCADE",
            name="fk_analytics_evidence_artifact",
        ),
        ForeignKeyConstraint(
            ["owner_id", "evidence_object_id", "evidence_revision"],
            [
                "health_object_revisions.owner_id",
                "health_object_revisions.object_id",
                "health_object_revisions.revision",
            ],
            ondelete="RESTRICT",
            name="fk_analytics_evidence_revision",
        ),
        CheckConstraint("evidence_revision > 0", name="ck_analytics_evidence_revision"),
        CheckConstraint(
            "evidence_object_type IN ('derived_signal', 'event', 'observation')",
            name="ck_analytics_evidence_object_type",
        ),
        Index(
            "ix_analytics_evidence_owner_source",
            "owner_id",
            "evidence_object_id",
            "evidence_revision",
        ),
    )


class PlanningLink(Base):
    """Owner-safe ordered plan items and explicit context relevance links."""

    __tablename__ = "planning_links"

    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    parent_object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    link_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    link_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    target_object_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    relevance: Mapped[str | None] = mapped_column(String(32))

    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "parent_object_id"],
            ["planning_resources.owner_id", "planning_resources.object_id"],
            ondelete="CASCADE",
            name="fk_planning_links_owner_parent",
        ),
        ForeignKeyConstraint(
            ["owner_id", "target_object_id"],
            ["health_objects.owner_id", "health_objects.id"],
            ondelete="RESTRICT",
            name="fk_planning_links_owner_target",
        ),
        CheckConstraint(
            "link_kind IN ('plan_goal', 'plan_regimen', 'plan_task', 'plan_retired', "
            "'context_goal', 'context_regimen', 'context_profile', 'context_relation')",
            name="ck_planning_links_kind",
        ),
        CheckConstraint(
            "link_kind = 'plan_retired' OR "
            "(link_kind = 'plan_task' AND target_object_id IS NULL) OR "
            "(link_kind NOT IN ('plan_task', 'plan_retired') AND target_object_id IS NOT NULL)",
            name="ck_planning_links_target",
        ),
        CheckConstraint("position >= 0", name="ck_planning_links_position"),
        CheckConstraint("priority BETWEEN 0 AND 100", name="ck_planning_links_priority"),
        UniqueConstraint(
            "owner_id", "parent_object_id", "position", name="uq_planning_links_position"
        ),
        Index("ix_planning_links_owner_target", "owner_id", "target_object_id"),
    )


class PlanningScheduleIdentity(Base):
    __tablename__ = "planning_schedule_identities"

    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    schedule_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    parent_object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    item_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "parent_object_id"],
            ["health_objects.owner_id", "health_objects.id"],
            ondelete="CASCADE",
            name="fk_planning_schedule_identity_owner_parent",
        ),
        ForeignKeyConstraint(
            ["owner_id", "parent_object_id", "item_id"],
            [
                "planning_links.owner_id",
                "planning_links.parent_object_id",
                "planning_links.link_id",
            ],
            ondelete="RESTRICT",
            name="fk_planning_schedule_identity_item",
        ),
        UniqueConstraint(
            "owner_id", "parent_object_id", "item_id", name="uq_planning_schedule_identity_item"
        ),
        Index(
            "uq_planning_schedule_identity_parent_without_item",
            "owner_id",
            "parent_object_id",
            unique=True,
            postgresql_where=item_id.is_(None),
        ),
        UniqueConstraint(
            "owner_id",
            "schedule_id",
            "parent_object_id",
            name="uq_planning_schedule_identity_parent",
        ),
    )


class PlanningSchedule(Base):
    """Immutable effective-dated versions sharing one stable schedule identity."""

    __tablename__ = "planning_schedules"

    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    schedule_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    revision: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    parent_object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    item_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "schedule_id", "parent_object_id"],
            [
                "planning_schedule_identities.owner_id",
                "planning_schedule_identities.schedule_id",
                "planning_schedule_identities.parent_object_id",
            ],
            ondelete="CASCADE",
            name="fk_planning_schedules_owner_identity",
        ),
        ForeignKeyConstraint(
            ["owner_id", "parent_object_id", "item_id"],
            [
                "planning_links.owner_id",
                "planning_links.parent_object_id",
                "planning_links.link_id",
            ],
            ondelete="RESTRICT",
            name="fk_planning_schedules_plan_item",
        ),
        CheckConstraint("revision > 0", name="ck_planning_schedules_revision"),
        CheckConstraint(
            "jsonb_typeof(definition) = 'object'", name="ck_planning_schedules_definition"
        ),
        UniqueConstraint(
            "owner_id", "schedule_id", "effective_from", name="uq_planning_schedules_effective"
        ),
        Index(
            "ix_planning_schedules_owner_parent_effective",
            "owner_id",
            "parent_object_id",
            "effective_from",
        ),
    )


class PlanningOccurrenceOverride(Base):
    __tablename__ = "planning_occurrence_overrides"

    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    occurrence_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    schedule_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    expected_schedule_revision: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    override_revision: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    rescheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    original_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    original_timezone: Mapped[str | None] = mapped_column(String(64))
    dst_resolution: Mapped[str | None] = mapped_column(String(24))
    linked_event_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    linked_observation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "schedule_id"],
            ["planning_schedule_identities.owner_id", "planning_schedule_identities.schedule_id"],
            ondelete="CASCADE",
            name="fk_occurrence_overrides_owner_schedule",
        ),
        ForeignKeyConstraint(
            ["owner_id", "linked_event_id"],
            ["events.owner_id", "events.object_id"],
            ondelete="RESTRICT",
            name="fk_occurrence_overrides_owner_event",
        ),
        ForeignKeyConstraint(
            ["owner_id", "linked_observation_id"],
            ["observations.owner_id", "observations.object_id"],
            ondelete="RESTRICT",
            name="fk_occurrence_overrides_owner_observation",
        ),
        CheckConstraint(
            "state IN ('completed', 'skipped', 'rescheduled')", name="ck_occurrence_overrides_state"
        ),
        CheckConstraint(
            "linked_event_id IS NULL OR linked_observation_id IS NULL",
            name="ck_occurrence_overrides_single_link",
        ),
        CheckConstraint(
            "override_revision > 0 AND expected_schedule_revision > 0",
            name="ck_occurrence_overrides_revision",
        ),
        CheckConstraint(
            "(state = 'rescheduled' AND rescheduled_at IS NOT NULL) OR "
            "(state IN ('completed', 'skipped'))",
            name="ck_occurrence_overrides_rescheduled",
        ),
        Index("ix_occurrence_overrides_owner_schedule", "owner_id", "schedule_id"),
    )


class PlanningOccurrenceAction(Base):
    __tablename__ = "planning_occurrence_actions"

    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    occurrence_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    revision: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    schedule_revision: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    actor_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    acted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    rescheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    linked_event_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    linked_observation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "occurrence_key"],
            [
                "planning_occurrence_overrides.owner_id",
                "planning_occurrence_overrides.occurrence_key",
            ],
            ondelete="CASCADE",
            name="fk_occurrence_actions_owner_override",
        ),
        ForeignKeyConstraint(
            ["actor_id"], ["users.id"], ondelete="RESTRICT", name="fk_occurrence_actions_actor"
        ),
        ForeignKeyConstraint(
            ["owner_id", "linked_event_id"],
            ["events.owner_id", "events.object_id"],
            ondelete="RESTRICT",
            name="fk_occurrence_actions_owner_event",
        ),
        ForeignKeyConstraint(
            ["owner_id", "linked_observation_id"],
            ["observations.owner_id", "observations.object_id"],
            ondelete="RESTRICT",
            name="fk_occurrence_actions_owner_observation",
        ),
        CheckConstraint(
            "revision > 0 AND schedule_revision > 0", name="ck_occurrence_actions_revision"
        ),
        CheckConstraint("actor_id = owner_id", name="ck_occurrence_actions_owner_actor"),
        CheckConstraint(
            "action IN ('completed', 'skipped', 'rescheduled')", name="ck_occurrence_actions_state"
        ),
        CheckConstraint(
            "linked_event_id IS NULL OR linked_observation_id IS NULL",
            name="ck_occurrence_actions_single_link",
        ),
    )


class TrackerSchemaVersion(Base):
    __tablename__ = "tracker_schema_versions"

    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tracker_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    version: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "tracker_id"],
            ["health_objects.owner_id", "health_objects.id"],
            ondelete="RESTRICT",
            name="fk_tracker_schema_versions_owner_tracker",
        ),
        CheckConstraint("version > 0", name="ck_tracker_schema_versions_version"),
        CheckConstraint(
            "jsonb_typeof(definition) = 'object'", name="ck_tracker_schema_versions_definition"
        ),
    )


class HealthRelationship(Base):
    __tablename__ = "health_relationships"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    from_object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    to_object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "from_object_id"],
            ["health_objects.owner_id", "health_objects.id"],
            ondelete="CASCADE",
            name="fk_health_relationships_owner_from",
        ),
        ForeignKeyConstraint(
            ["owner_id", "to_object_id"],
            ["health_objects.owner_id", "health_objects.id"],
            ondelete="CASCADE",
            name="fk_health_relationships_owner_to",
        ),
        ForeignKeyConstraint(
            ["owner_id", "source_id"],
            ["sources.owner_id", "sources.id"],
            ondelete="RESTRICT",
            name="fk_health_relationships_owner_source",
        ),
        CheckConstraint("from_object_id <> to_object_id", name="ck_health_relationships_not_self"),
        CheckConstraint("relation_type = 'related_to'", name="ck_health_relationships_type_phase1"),
        CheckConstraint(
            "valid_from IS NULL OR valid_to IS NULL OR valid_from < valid_to",
            name="ck_health_relationships_validity",
        ),
        UniqueConstraint(
            "owner_id",
            "from_object_id",
            "to_object_id",
            "relation_type",
            name="uq_health_relationships_edge",
        ),
        Index("ix_health_relationships_owner_from", "owner_id", "from_object_id"),
        Index("ix_health_relationships_owner_to", "owner_id", "to_object_id"),
    )
