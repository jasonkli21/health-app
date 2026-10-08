from uuid import UUID

import pytest
from health_api.config.settings import Settings, migration_database_url
from pydantic import ValidationError

POOL_URL = "postgresql+psycopg://api:secret@ep-health-pooler.us-east-2.aws.neon.tech/health?sslmode=verify-full"
DIRECT_URL = "postgresql+psycopg://migrator:secret@ep-health.us-east-2.aws.neon.tech/health?sslmode=verify-full"


def test_settings_allow_an_unconfigured_local_principal_for_fail_closed_routes() -> None:
    settings = Settings(_env_file=None, app_env="local", auth_mode="dev")
    assert settings.local_principal_id is None


def test_personal_ai_enabled_is_rejected_until_the_integration_contract_is_implemented() -> None:
    with pytest.raises(ValidationError, match="Application Integration Contract"):
        Settings(_env_file=None, personal_ai_enabled=True)


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


def test_firebase_test_mode_requires_explicit_project_and_keeps_dev_identity_disabled() -> None:
    settings = Settings(
        _env_file=None, app_env="test", auth_mode="firebase", firebase_project_id="health-dev-1234"
    )
    assert settings.local_principal_id is None
    assert settings.auth_mode == "firebase"


def test_local_settings_hide_database_credentials_from_repr() -> None:
    settings = Settings(
        _env_file=None, database_url="postgresql://user:private-pass@localhost/health"
    )
    assert "private-pass" not in repr(settings)


def test_cloud_migration_uses_only_the_explicit_direct_url() -> None:
    assert migration_database_url("cloud", DIRECT_URL, None) == DIRECT_URL
    with pytest.raises(ValueError, match="MIGRATION_DATABASE_URL is required"):
        migration_database_url("cloud", None, None)
    with pytest.raises(ValueError, match="direct, non-pooled"):
        migration_database_url("cloud", POOL_URL, None)


def test_migration_environment_rejects_unknown_mode_and_uses_local_database() -> None:
    assert migration_database_url("local", None, "postgresql://localhost/health") == (
        "postgresql://localhost/health"
    )
    with pytest.raises(ValueError, match="APP_ENV"):
        migration_database_url("production", DIRECT_URL, None)


def test_cloud_requires_verified_firebase_and_gcs_configuration() -> None:
    with pytest.raises(ValidationError, match="FIREBASE_PROJECT_ID"):
        Settings(_env_file=None, app_env="cloud", auth_mode="firebase")


def test_cloud_rejects_dev_auth_and_local_principal() -> None:
    with pytest.raises(ValidationError, match="development authentication"):
        Settings(_env_file=None, app_env="cloud", auth_mode="dev")
    with pytest.raises(ValidationError, match="LOCAL_PRINCIPAL_ID"):
        _cloud_settings(local_principal_id="00000000-0000-0000-0000-000000000001")


def test_cloud_pool_is_bounded_by_explicit_connection_budget() -> None:
    settings = _cloud_settings(database_connection_budget=20)
    assert 2 * settings.database_pool_size * settings.cloud_max_instances == 20
    with pytest.raises(ValidationError, match="DATABASE_CONNECTION_BUDGET"):
        _cloud_settings(database_connection_budget=19)


def test_cloud_requires_pooled_runtime_url_and_verified_tls() -> None:
    assert _cloud_settings().database_url.get_secret_value() == POOL_URL
    with pytest.raises(ValidationError, match="sslmode=verify-full"):
        _cloud_settings(database_url=POOL_URL.replace("verify-full", "require"))
    with pytest.raises(ValidationError, match="pooled endpoint"):
        _cloud_settings(database_url=DIRECT_URL)


def test_cloud_requires_gcs_backend_and_valid_project_and_bucket_names() -> None:
    with pytest.raises(ValidationError, match="OBJECT_STORAGE_BACKEND=gcs"):
        _cloud_settings(object_storage_backend="local")
    with pytest.raises(ValidationError, match="Google Cloud project ID"):
        _cloud_settings(gcp_project_id="Not A Project")
    with pytest.raises(ValidationError, match="Cloud Storage bucket name"):
        _cloud_settings(gcs_bucket="Health Data")


def _cloud_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "app_env": "cloud",
        "auth_mode": "firebase",
        "object_storage_backend": "gcs",
        "firebase_project_id": "health-prod-1234",
        "gcp_project_id": "health-cloud-1234",
        "gcs_bucket": "health-prod-private-objects",
        "database_url": POOL_URL,
        "cloud_max_instances": 2,
        "database_connection_budget": 20,
    }
    values.update(overrides)
    return Settings(**values)
