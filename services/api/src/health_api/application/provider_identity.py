"""Persist verified external subjects as stable internal owner identities."""

from __future__ import annotations

from uuid import UUID, uuid4

from health_api.persistence.models import ProviderIdentity, User
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session


def resolve_provider_identity(
    session: Session, *, issuer: str, subject: str, display_timezone: str
) -> UUID | None:
    """Create one principal on first login, safely coalescing concurrent attempts."""
    if not issuer or len(issuer) > 256 or not subject or len(subject) > 128:
        return None

    with session.begin():
        current = session.get(ProviderIdentity, (issuer, subject))
        if current is not None:
            owner = session.get(User, current.user_id)
            if owner is None or owner.lifecycle != "active":
                return None
            return owner.id

        candidate_id = uuid4()
        candidate = User(id=candidate_id, display_timezone=display_timezone)
        session.add(candidate)
        session.flush()

        inserted_user_id = session.execute(
            insert(ProviderIdentity)
            .values(issuer=issuer, subject=subject, user_id=candidate_id)
            .on_conflict_do_nothing(
                index_elements=[ProviderIdentity.issuer, ProviderIdentity.subject]
            )
            .returning(ProviderIdentity.user_id)
        ).scalar_one_or_none()

        if inserted_user_id is None:
            session.delete(candidate)
            session.flush()
            current = session.get(ProviderIdentity, (issuer, subject))
            if current is None:
                return None
            owner = session.get(User, current.user_id)
            if owner is None or owner.lifecycle != "active":
                return None
            return owner.id

        return inserted_user_id
