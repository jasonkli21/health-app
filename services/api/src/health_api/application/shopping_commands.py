"""Build a note from the same narrow ergonomic export used by federation authority."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from health_api.application.personal_ai_federation_export import (
    HealthFederationExportDenied,
    read_health_federation_export,
)
from health_api.integrations.federation_export import (
    ErgonomicConstraintsPayload,
    HealthFederationExportRecord,
    HealthFederationExportRequest,
)
from health_api.integrations.task_wire import DelegatedSourceCommand
from health_api.persistence.models import HealthObject, User
from health_api.persistence.source_commands import DelegatedSourceCommand as CommandRow


class ErgonomicTaskChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: UUID
    object_id: UUID
    expected_source_version: str = Field(pattern=r"^health-object-v1:r[0-9]+:schema-[0-9]+$")
    context_choice_id: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")
    shopping_project_id: UUID
    expected_project_revision: int = Field(strict=True, ge=1, le=10**18 - 1)


class ShoppingCommandService:
    def __init__(self, session: Session, owner_id: UUID):
        self.session, self.owner_id = session, owner_id

    def owned(self, command_id: UUID) -> CommandRow:
        user = self.session.scalar(
            select(User).where(User.id == self.owner_id).with_for_update(read=True)
        )
        if user is None or user.lifecycle != "active":
            raise HTTPException(401, "task_identity_denied")
        row = self.session.get(CommandRow, command_id)
        if row is None or row.owner_id != self.owner_id:
            raise HTTPException(404, "command_not_found")
        return row

    def _export(self, object_id: UUID, version: str) -> HealthFederationExportRecord:
        self.session.scalar(
            select(HealthObject)
            .where(HealthObject.id == object_id, HealthObject.owner_id == self.owner_id)
            .with_for_update()
        )
        try:
            result = read_health_federation_export(
                self.session,
                self.owner_id,
                HealthFederationExportRequest(
                    operation="read",
                    entity_id=object_id,
                    category="ergonomic_constraints",
                    purpose="health_ergonomic_constraints_to_shopping",
                    destination_application_id="shopping",
                    fields=("ergonomic_constraints",),
                    max_bytes=4096,
                ),
            )
        except HealthFederationExportDenied as error:
            raise HTTPException(409, "health_consent_or_revision_changed") from error
        if (
            result.item is None
            or result.item.source_version != version
            or result.authoritative_empty
        ):
            raise HTTPException(409, "health_consent_or_revision_changed")
        return result.item

    def current(self, command_id: UUID) -> DelegatedSourceCommand:
        command = DelegatedSourceCommand.model_validate(self.owned(command_id).command)
        self._export(UUID(command.source_entity_id), command.expected_source_version)
        return command

    def create(self, choice: ErgonomicTaskChoice, fingerprint: str) -> DelegatedSourceCommand:
        key = int.from_bytes(sha256(choice.command_id.bytes).digest()[:8], "big", signed=True)
        self.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
        existing = self.session.get(CommandRow, choice.command_id)
        if existing is not None:
            command = DelegatedSourceCommand.model_validate(self.owned(choice.command_id).command)
            if (
                command.source_entity_id != str(choice.object_id)
                or command.expected_source_version != choice.expected_source_version
                or command.context_choice_id != choice.context_choice_id
                or command.target_entity_id != choice.shopping_project_id
                or command.expected_domain_version != str(choice.expected_project_revision)
            ):
                raise HTTPException(409, "command_idempotency_conflict")
            return command
        item = self._export(choice.object_id, choice.expected_source_version)
        if not isinstance(item.payload, ErgonomicConstraintsPayload):
            raise HTTPException(409, "health_source_invalid")
        values = item.payload.ergonomic_constraints
        content = "Ergonomic constraints: " + (
            "; ".join(values) if isinstance(values, tuple) else values or ""
        )
        if len(content) > 1000:
            raise HTTPException(422, "shared_context_too_large")
        command = DelegatedSourceCommand(
            source_application_id="health",
            command_id=choice.command_id,
            context_choice_id=choice.context_choice_id,
            source_entity_type="profile_item",
            source_entity_id=str(choice.object_id),
            expected_source_version=item.source_version,
            target_entity_id=choice.shopping_project_id,
            expected_domain_version=str(choice.expected_project_revision),
            operation_id="project.append_context_note",
            operation_version=1,
            operation_contract_fingerprint=fingerprint,
            payload_schema_id="shopping-context-note-v1",
            payload={"content": content},
            rationale="Append only the explicitly shared ergonomic constraints.",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
        self.session.add(
            CommandRow(
                command_id=choice.command_id,
                owner_id=self.owner_id,
                command=command.model_dump(mode="json"),
                created_at=datetime.now(UTC),
            )
        )
        self.session.flush()
        return command

    def bind(self, command_id: UUID, proposal_id: UUID) -> None:
        row = self.owned(command_id)
        if row.proposal_id is not None and row.proposal_id != proposal_id:
            raise HTTPException(409, "command_proposal_conflict")
        row.proposal_id = proposal_id
        self.session.flush()
