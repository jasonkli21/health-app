from uuid import UUID

import pytest
from pydantic import ValidationError

from health_api.config.settings import Settings


def test_settings_allow_an_unconfigured_local_principal_for_fail_closed_routes() -> None:
    settings = Settings(_env_file=None, app_env="local", auth_mode="dev")
    assert settings.local_principal_id is None


def test_settings_accept_explicit_local_principal_and_iana_timezone() -> None:
    settings = Settings(
        _env_file=None,
        app_env="local",
        auth_mode="dev",
        local_principal_id="00000000-0000-0000-0000-000000000001",
        local_principal_timezone="America/Los_Angeles",
    )
    assert settings.local_principal_id == UUID("00000000-0000-0000-0000-000000000001")


def test_development_auth_is_not_allowed_outside_local_and_test() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production", auth_mode="dev")


def test_invalid_iana_timezone_is_rejected() -> None:
    with pytest.raises(ValidationError, match="IANA timezone"):
        Settings(_env_file=None, local_principal_timezone="Mars/Olympus_Mons")
