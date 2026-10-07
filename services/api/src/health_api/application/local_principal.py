"""Resolve the configured local principal without accepting identity from a request."""

from uuid import UUID

from health_api.config.settings import Settings
from health_api.persistence.models import User
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session


def ensure_local_principal(
    session: Session, settings: Settings, *, allow_erasure_status: bool = False
) -> UUID | None:
    principal_id = settings.local_principal_id
    if principal_id is None:
        return None

    with session.begin():
        session.execute(
            insert(User)
            .values(id=principal_id, display_timezone=settings.local_principal_timezone)
            .on_conflict_do_nothing(index_elements=[User.id])
        )
        principal = session.get(User, principal_id)
        allowed_lifecycle = {"active"}
        if allow_erasure_status:
            allowed_lifecycle.update({"deleting", "erased"})
        if principal is None or principal.lifecycle not in allowed_lifecycle:
            return None
        if (
            principal.lifecycle == "active"
            and principal.display_timezone != settings.local_principal_timezone
        ):
            principal.display_timezone = settings.local_principal_timezone
    return principal_id
