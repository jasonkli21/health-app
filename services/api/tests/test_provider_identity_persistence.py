from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from health_api.application.provider_identity import resolve_provider_identity
from health_api.persistence.models import ProviderIdentity, User
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def test_concurrent_first_logins_create_one_internal_principal(
    postgres_engine: Engine, db_session: Session
) -> None:
    assert db_session.scalar(select(func.count()).select_from(User)) == 0
    factory = sessionmaker(bind=postgres_engine, expire_on_commit=False)
    issuer = "https://securetoken.google.com/health-test-1234"
    subject = "same-firebase-subject"

    def login() -> object:
        with factory() as session:
            return resolve_provider_identity(
                session,
                issuer=issuer,
                subject=subject,
                display_timezone="America/Los_Angeles",
            )

    with ThreadPoolExecutor(max_workers=8) as pool:
        owners = list(pool.map(lambda _index: login(), range(8)))

    assert owners[0] is not None
    assert set(owners) == {owners[0]}
    assert db_session.scalar(select(func.count()).select_from(ProviderIdentity)) == 1
    assert db_session.scalar(select(func.count()).select_from(User)) == 1
