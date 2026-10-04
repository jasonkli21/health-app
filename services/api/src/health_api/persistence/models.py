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
    func,
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
    observation_item: Mapped[ObservationItem | None] = relationship(
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
            "object_type IN ('profile_item', 'event', 'observation')",
            name="ck_health_objects_type",
        ),
        CheckConstraint(
            "(object_type = 'profile_item' AND domain = 'profile') OR "
            "(object_type = 'event' AND domain IN ('nutrition', 'exercise', 'sleep', 'symptoms')) OR "
            "(object_type = 'observation' AND domain IN ('measurements', 'symptoms'))",
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
    )


class HealthObjectRevision(Base):
    __tablename__ = "health_object_revisions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    object_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
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
    numeric_value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    health_object: Mapped[HealthObject] = relationship(back_populates="observation_item")

    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "object_id"],
            ["health_objects.owner_id", "health_objects.id"],
            ondelete="CASCADE",
            name="fk_observations_owner_object",
        ),
        CheckConstraint(
            "metric_key IN ('weight', 'temperature', 'systolic_pressure', "
            "'diastolic_pressure', 'pulse', 'symptom_severity')",
            name="ck_observations_metric",
        ),
        CheckConstraint(
            "(metric_key = 'weight' AND unit IN ('kg', 'lb')) OR "
            "(metric_key = 'temperature' AND unit IN ('C', 'F')) OR "
            "(metric_key IN ('systolic_pressure', 'diastolic_pressure') AND unit = 'mmHg') OR "
            "(metric_key = 'pulse' AND unit = 'bpm') OR "
            "(metric_key = 'symptom_severity' AND unit = 'score')",
            name="ck_observations_metric_unit",
        ),
        CheckConstraint(
            "numeric_value > '-Infinity'::double precision AND "
            "numeric_value < 'Infinity'::double precision AND "
            "(metric_key <> 'symptom_severity' OR "
            "(numeric_value >= 0 AND numeric_value <= 10 AND numeric_value = trunc(numeric_value)))",
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
            "jsonb_typeof(payload) = 'object' AND payload ? 'value' AND "
            "jsonb_typeof(payload->'value') = 'object' AND "
            "payload->'value' ? 'metric' AND "
            "jsonb_typeof(payload->'value'->'metric') = 'string' AND "
            "payload->'value'->>'metric' = metric_key AND "
            "payload->'value' ? 'unit' AND "
            "jsonb_typeof(payload->'value'->'unit') = 'string' AND "
            "payload->'value'->>'unit' = unit AND "
            "payload->'value' ? 'value' AND "
            "jsonb_typeof(payload->'value'->'value') = 'number' AND "
            "(payload->'value'->>'value')::double precision = numeric_value",
            name="ck_observations_payload_consistency",
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
