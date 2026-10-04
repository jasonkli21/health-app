"""PostgreSQL tables for the Phase 1 Profile vertical slice."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
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

    __table_args__ = (
        CheckConstraint("lifecycle IN ('active', 'disabled')", name="ck_users_lifecycle"),
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
        CheckConstraint("object_type = 'profile_item'", name="ck_health_objects_type_phase1"),
        CheckConstraint("domain = 'profile'", name="ck_health_objects_domain_phase1"),
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
            "payload->>'kind' = kind AND payload->>'category' = category AND "
            "payload->>'key' = key",
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
