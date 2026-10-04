"""Owner-scoped Profile persistence and transaction boundaries."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import and_, delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from health_api.application.envelope_service import manual_source
from health_api.application.errors import ProfileConflict, ProfileNotFound, ProfileValidationError
from health_api.domain.schemas import (
    ProfileMetadata,
    ProfilePayloadV1,
    ProfileSchemaRegistry,
    ProfileValidity,
)
from health_api.persistence.models import (
    HealthObject,
    HealthObjectRevision,
    HealthRelationship,
    ProfileItem,
    Source,
)


@dataclass(frozen=True)
class CreateProfile:
    id: UUID
    profile: ProfilePayloadV1
    validity: ProfileValidity
    ai_use_allowed: bool = False
    cross_domain_use_allowed: bool = False
    notes: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class CreateProfileResult:
    aggregate: tuple[HealthObject, ProfileItem, Source]
    created: bool


type ProfileAggregate = tuple[HealthObject, ProfileItem, Source]


def _metadata_payload(value: object | None) -> dict[str, Any]:
    try:
        return ProfileMetadata.model_validate(value or {}).root
    except ValidationError as exc:
        raise ProfileValidationError("metadata is invalid or exceeds its size limits") from exc


def _canonical_create_content(command: CreateProfile) -> str:
    content = {
        "profile": command.profile.model_dump(mode="json"),
        "valid_from": command.validity.valid_from.isoformat()
        if command.validity.valid_from
        else None,
        "valid_to": command.validity.valid_to.isoformat() if command.validity.valid_to else None,
        "ai_use_allowed": command.ai_use_allowed,
        "cross_domain_use_allowed": command.cross_domain_use_allowed,
        "notes": command.notes,
        "metadata": _metadata_payload(command.metadata),
    }
    return json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _fingerprint(command: CreateProfile) -> str:
    return hashlib.sha256(_canonical_create_content(command).encode("utf-8")).hexdigest()


def _select_aggregate(session: Session, owner_id: UUID, object_id: UUID) -> ProfileAggregate | None:
    statement = (
        select(HealthObject, ProfileItem, Source)
        .join(
            ProfileItem,
            and_(
                ProfileItem.owner_id == HealthObject.owner_id,
                ProfileItem.object_id == HealthObject.id,
            ),
        )
        .join(
            Source,
            and_(Source.owner_id == HealthObject.owner_id, Source.id == HealthObject.source_id),
        )
        .where(HealthObject.owner_id == owner_id, HealthObject.id == object_id)
    )
    result = session.execute(statement).one_or_none()
    if result is None:
        return None
    return result[0], result[1], result[2]


def _snapshot(
    health_object: HealthObject, profile_item: ProfileItem, source: Source
) -> dict[str, Any]:
    return {
        "object_type": health_object.object_type,
        "domain": health_object.domain,
        "status": health_object.status,
        "title": health_object.title,
        "valid_from": health_object.valid_from.isoformat() if health_object.valid_from else None,
        "valid_to": health_object.valid_to.isoformat() if health_object.valid_to else None,
        "recorded_at": health_object.recorded_at.isoformat(),
        "created_at": health_object.created_at.isoformat(),
        "updated_at": health_object.updated_at.isoformat(),
        "source": {"id": str(source.id), "kind": source.source_kind, "name": source.display_name},
        "confirmation_status": health_object.confirmation_status,
        "schema_version": health_object.schema_version,
        "revision": health_object.revision,
        "notes": health_object.notes,
        "metadata": health_object.metadata_json,
        "permissions": {
            "ai_use_allowed": health_object.ai_use_allowed,
            "cross_domain_use_allowed": health_object.cross_domain_use_allowed,
        },
        "profile": profile_item.payload,
    }


def _append_revision(
    session: Session,
    owner_id: UUID,
    aggregate: ProfileAggregate,
    reason: str,
) -> None:
    health_object, profile_item, source = aggregate
    session.add(
        HealthObjectRevision(
            owner_id=owner_id,
            object_id=health_object.id,
            revision=health_object.revision,
            actor_kind="user",
            actor_id=owner_id,
            reason=reason,
            snapshot=_snapshot(health_object, profile_item, source),
        )
    )


def create_profile_item(
    session: Session, owner_id: UUID, command: CreateProfile
) -> CreateProfileResult:
    fingerprint = _fingerprint(command)
    try:
        with session.begin():
            existing = session.scalar(
                select(HealthObject).where(
                    HealthObject.owner_id == owner_id, HealthObject.id == command.id
                )
            )
            if existing is not None:
                if existing.create_fingerprint != fingerprint:
                    raise ProfileConflict("this ID was already used for different content")
                aggregate = _select_aggregate(session, owner_id, command.id)
                if aggregate is None:
                    raise RuntimeError("profile envelope has no profile payload")
                return CreateProfileResult(aggregate, False)

            source = manual_source(session, owner_id)
            payload = command.profile.model_dump(mode="json")
            health_object = HealthObject(
                id=command.id,
                owner_id=owner_id,
                object_type="profile_item",
                domain="profile",
                status="active",
                title=command.profile.label,
                valid_from=command.validity.valid_from,
                valid_to=command.validity.valid_to,
                source_id=source.id,
                confirmation_status="user_confirmed",
                schema_version=1,
                revision=1,
                notes=command.notes,
                metadata_json=_metadata_payload(command.metadata),
                ai_use_allowed=command.ai_use_allowed,
                cross_domain_use_allowed=command.cross_domain_use_allowed,
                create_fingerprint=fingerprint,
            )
            profile_item = ProfileItem(
                owner_id=owner_id,
                object_id=command.id,
                kind=command.profile.kind.value,
                category=command.profile.category.value,
                key=command.profile.key,
                payload=payload,
            )
            session.add_all([health_object, profile_item])
            session.flush()
            aggregate = (health_object, profile_item, source)
            _append_revision(session, owner_id, aggregate, "create")
            session.flush()
            return CreateProfileResult(aggregate, True)
    except IntegrityError as exc:
        session.rollback()
        existing = session.scalar(
            select(HealthObject).where(
                HealthObject.owner_id == owner_id, HealthObject.id == command.id
            )
        )
        if existing is not None and existing.create_fingerprint == fingerprint:
            aggregate = _select_aggregate(session, owner_id, command.id)
            if aggregate is not None:
                return CreateProfileResult(aggregate, False)
        if existing is not None:
            raise ProfileConflict("this ID was already used for different content") from exc
        collision = session.scalar(select(HealthObject.id).where(HealthObject.id == command.id))
        if collision is not None:
            raise ProfileConflict("this ID is unavailable") from exc
        raise


def get_profile_item(session: Session, owner_id: UUID, object_id: UUID) -> ProfileAggregate:
    aggregate = _select_aggregate(session, owner_id, object_id)
    if aggregate is None:
        raise ProfileNotFound
    return aggregate


def list_profile_items(
    session: Session,
    owner_id: UUID,
    as_of: datetime,
    category: str | None,
    limit: int,
    after: tuple[datetime, UUID] | None = None,
) -> list[ProfileAggregate]:
    conditions = [
        HealthObject.owner_id == owner_id,
        HealthObject.status == "active",
        or_(HealthObject.valid_from.is_(None), HealthObject.valid_from <= as_of),
        or_(HealthObject.valid_to.is_(None), HealthObject.valid_to > as_of),
    ]
    if category is not None:
        conditions.append(ProfileItem.category == category)
    if after is not None:
        conditions.append(
            or_(
                HealthObject.created_at < after[0],
                and_(HealthObject.created_at == after[0], HealthObject.id < after[1]),
            )
        )
    statement = (
        select(HealthObject, ProfileItem, Source)
        .join(
            ProfileItem,
            and_(
                ProfileItem.owner_id == HealthObject.owner_id,
                ProfileItem.object_id == HealthObject.id,
            ),
        )
        .join(
            Source,
            and_(Source.owner_id == HealthObject.owner_id, Source.id == HealthObject.source_id),
        )
        .where(*conditions)
        .order_by(HealthObject.created_at.desc(), HealthObject.id.desc())
        .limit(limit)
    )
    return [(row[0], row[1], row[2]) for row in session.execute(statement).all()]


def list_profile_history(
    session: Session, owner_id: UUID, object_id: UUID, after_revision: int, limit: int
) -> list[HealthObjectRevision]:
    get_profile_item(session, owner_id, object_id)
    statement = (
        select(HealthObjectRevision)
        .where(
            HealthObjectRevision.owner_id == owner_id,
            HealthObjectRevision.object_id == object_id,
            HealthObjectRevision.revision > after_revision,
        )
        .order_by(HealthObjectRevision.revision.asc())
        .limit(limit)
    )
    return list(session.scalars(statement).all())


def update_profile_item(
    session: Session,
    owner_id: UUID,
    object_id: UUID,
    expected_revision: int,
    changes: dict[str, Any],
) -> ProfileAggregate:
    with session.begin():
        health_object = session.scalar(
            select(HealthObject)
            .where(HealthObject.owner_id == owner_id, HealthObject.id == object_id)
            .with_for_update()
        )
        if health_object is None:
            raise ProfileNotFound
        if health_object.status != "active":
            raise ProfileConflict("archived Profile items cannot be edited")
        if health_object.revision != expected_revision:
            raise ProfileConflict("Profile item has changed; reload before saving")

        profile_item = session.scalar(
            select(ProfileItem).where(
                ProfileItem.owner_id == owner_id, ProfileItem.object_id == object_id
            )
        )
        if profile_item is None:
            raise RuntimeError("profile envelope has no profile payload")

        if "profile" in changes:
            profile_input = changes["profile"]
            if profile_input is None:
                raise ProfileConflict("profile content cannot be cleared")
            try:
                profile = ProfileSchemaRegistry.validate("profile_item", 1, profile_input)
            except ValidationError as exc:
                raise ProfileValidationError("Profile payload is invalid") from exc
        else:
            try:
                profile = ProfileSchemaRegistry.validate("profile_item", 1, profile_item.payload)
            except ValidationError as exc:
                raise ProfileValidationError("stored Profile payload is invalid") from exc
        assert isinstance(profile, ProfilePayloadV1)

        try:
            validity = ProfileValidity(
                valid_from=changes.get("valid_from", health_object.valid_from),
                valid_to=changes.get("valid_to", health_object.valid_to),
            )
        except ValidationError as exc:
            raise ProfileValidationError("Profile validity window is invalid") from exc
        payload = profile.model_dump(mode="json")
        profile_item.kind = profile.kind.value
        profile_item.category = profile.category.value
        profile_item.key = profile.key
        profile_item.payload = payload
        health_object.title = profile.label
        health_object.valid_from = validity.valid_from
        health_object.valid_to = validity.valid_to
        if "notes" in changes:
            health_object.notes = changes["notes"]
        if "metadata" in changes:
            health_object.metadata_json = _metadata_payload(changes["metadata"])
        if "ai_use_allowed" in changes:
            health_object.ai_use_allowed = changes["ai_use_allowed"]
        if "cross_domain_use_allowed" in changes:
            health_object.cross_domain_use_allowed = changes["cross_domain_use_allowed"]
        health_object.revision += 1
        health_object.updated_at = datetime.now(UTC)
        session.flush()
        aggregate = _select_aggregate(session, owner_id, object_id)
        if aggregate is None:
            raise RuntimeError("updated Profile item could not be reloaded")
        _append_revision(session, owner_id, aggregate, "update")
        session.flush()
        return aggregate


def archive_profile_item(
    session: Session, owner_id: UUID, object_id: UUID, expected_revision: int
) -> ProfileAggregate:
    with session.begin():
        health_object = session.scalar(
            select(HealthObject)
            .where(HealthObject.owner_id == owner_id, HealthObject.id == object_id)
            .with_for_update()
        )
        if health_object is None:
            raise ProfileNotFound
        if health_object.revision != expected_revision:
            raise ProfileConflict("Profile item has changed; reload before saving")
        if health_object.status == "archived":
            raise ProfileConflict("Profile item is already archived")

        health_object.status = "archived"
        health_object.revision += 1
        health_object.updated_at = datetime.now(UTC)
        session.flush()
        aggregate = _select_aggregate(session, owner_id, object_id)
        if aggregate is None:
            raise RuntimeError("archived Profile item could not be reloaded")
        _append_revision(session, owner_id, aggregate, "archive")
        session.flush()
        return aggregate


def create_profile_relationship(
    session: Session,
    owner_id: UUID,
    from_object_id: UUID,
    to_object_id: UUID,
    relation_type: str,
    validity: ProfileValidity,
) -> HealthRelationship:
    if relation_type != "related_to":
        raise ProfileValidationError("unsupported relationship type")
    if from_object_id == to_object_id:
        raise ProfileValidationError("a Profile item cannot relate to itself")

    with session.begin():
        endpoints = set(
            session.scalars(
                select(HealthObject.id).where(
                    HealthObject.owner_id == owner_id,
                    HealthObject.id.in_([from_object_id, to_object_id]),
                )
            ).all()
        )
        if endpoints != {from_object_id, to_object_id}:
            raise ProfileNotFound
        source = manual_source(session, owner_id)
        relationship = HealthRelationship(
            id=uuid4(),
            owner_id=owner_id,
            from_object_id=from_object_id,
            to_object_id=to_object_id,
            relation_type=relation_type,
            source_id=source.id,
            valid_from=validity.valid_from,
            valid_to=validity.valid_to,
        )
        session.add(relationship)
        session.flush()
        return relationship


def list_profile_relationships(
    session: Session, owner_id: UUID, object_id: UUID
) -> list[HealthRelationship]:
    if (
        session.scalar(
            select(HealthObject.id).where(
                HealthObject.owner_id == owner_id, HealthObject.id == object_id
            )
        )
        is None
    ):
        raise ProfileNotFound
    statement = (
        select(HealthRelationship)
        .where(
            HealthRelationship.owner_id == owner_id,
            or_(
                HealthRelationship.from_object_id == object_id,
                HealthRelationship.to_object_id == object_id,
            ),
        )
        .order_by(HealthRelationship.created_at, HealthRelationship.id)
    )
    return list(session.scalars(statement).all())


def remove_profile_relationship(session: Session, owner_id: UUID, relationship_id: UUID) -> None:
    with session.begin():
        deleted_id = session.execute(
            delete(HealthRelationship)
            .where(
                HealthRelationship.owner_id == owner_id,
                HealthRelationship.id == relationship_id,
            )
            .returning(HealthRelationship.id)
        ).scalar_one_or_none()
        if deleted_id is None:
            raise ProfileNotFound
