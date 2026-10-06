"""Validated server-only configuration for portable local and cloud operation."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url

from health_api.domain.proposals import MAX_PROPOSAL_LIFETIME_HOURS
from health_api.domain.schemas import validate_iana_timezone


def _postgres_url(value: str | SecretStr) -> URL:
    raw = value.get_secret_value() if isinstance(value, SecretStr) else value
    try:
        return make_url(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("must be a valid PostgreSQL connection URL") from exc


def validate_cloud_database_url(value: str | SecretStr, *, direct: bool) -> None:
    url = _postgres_url(value)
    if url.drivername not in {"postgresql", "postgresql+psycopg"}:
        raise ValueError("cloud database URLs must use PostgreSQL with psycopg")
    if not url.host or url.host.endswith(("localhost", ".localhost")) or url.host == "127.0.0.1":
        raise ValueError("cloud database URLs must use the configured Neon endpoint")
    if not url.host.endswith(".neon.tech"):
        raise ValueError("cloud database URLs must use the configured Neon endpoint")
    if url.query.get("sslmode") != "verify-full":
        raise ValueError("cloud database URLs must require verified TLS with sslmode=verify-full")
    pooled = "-pooler." in url.host
    if direct and pooled:
        raise ValueError("migration database URLs must use the direct, non-pooled endpoint")
    if not direct and not pooled:
        raise ValueError("runtime database URLs must use Neon's pooled endpoint")


def migration_database_url(
    app_env: str, direct_url: str | None, local_database_url: str | None
) -> str:
    """Resolve the direct migration endpoint without loading runtime secrets in cloud."""
    normalized_env = app_env.lower()
    if normalized_env not in {"local", "test", "cloud"}:
        raise ValueError("APP_ENV must be local, test, or cloud")
    if normalized_env == "cloud":
        if not direct_url:
            raise ValueError("MIGRATION_DATABASE_URL is required for cloud releases")
        validate_cloud_database_url(direct_url, direct=True)
        return direct_url
    if direct_url:
        return direct_url
    if not local_database_url:
        raise ValueError("a database URL is required for migrations")
    return local_database_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["local", "test", "cloud"] = "local"
    database_url: SecretStr = Field(
        default=SecretStr("postgresql+psycopg://health:health@127.0.0.1:5432/health"),
        min_length=1,
        repr=False,
    )
    auth_mode: Literal["dev", "firebase"] = "dev"
    object_storage_backend: Literal["local", "gcs"] = "local"
    local_principal_id: UUID | None = None
    local_principal_timezone: str = "America/Los_Angeles"
    local_object_storage_root: Path = Path(".data/objects")
    max_object_size_bytes: int = Field(default=10_485_760, ge=1, le=52_428_800)
    object_storage_timeout_seconds: int = Field(default=10, ge=1, le=30)
    firebase_project_id: str | None = None
    gcp_project_id: str | None = None
    gcs_bucket: str | None = None
    database_pool_size: int = Field(default=5, ge=1, le=20)
    database_max_overflow: int = Field(default=0, ge=0, le=5)
    database_pool_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    database_connect_timeout_seconds: int = Field(default=5, ge=1, le=15)
    cloud_max_instances: int | None = Field(default=None, ge=1, le=100)
    database_connection_budget: int | None = Field(default=None, ge=1, le=5000)
    auth_http_timeout_seconds: int = Field(default=4, ge=1, le=15)
    auth_max_in_flight: int = Field(default=32, ge=1, le=128)
    personal_ai_enabled: bool = False
    action_proposal_generation_enabled: bool = True
    action_proposal_ttl_hours: int = Field(default=24, ge=1, le=MAX_PROPOSAL_LIFETIME_HOURS)

    @field_validator("local_principal_timezone")
    @classmethod
    def timezone_must_be_iana(cls, value: str) -> str:
        return validate_iana_timezone(value)

    @field_validator("firebase_project_id")
    @classmethod
    def firebase_project_id_is_well_formed(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", value):
            raise ValueError("must be a Firebase project ID")
        return value

    @field_validator("gcp_project_id")
    @classmethod
    def gcp_project_id_is_well_formed(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", value):
            raise ValueError("must be a Google Cloud project ID")
        return value

    @field_validator("gcs_bucket")
    @classmethod
    def gcs_bucket_is_present_when_set(cls, value: str | None) -> str | None:
        if value is not None and (
            not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]", value) or ".." in value
        ):
            raise ValueError("must be a valid Cloud Storage bucket name")
        return value

    @model_validator(mode="after")
    def environment_settings_are_congruent(self) -> Settings:
        if self.auth_mode == "dev" and self.app_env not in {"local", "test"}:
            raise ValueError("development authentication is allowed only in local or test mode")
        if self.auth_mode == "firebase" and not self.firebase_project_id:
            raise ValueError("FIREBASE_PROJECT_ID is required when AUTH_MODE=firebase")
        if self.personal_ai_enabled:
            raise ValueError(
                "PERSONAL_AI_ENABLED cannot be true until the Personal AI service contract is configured"
            )

        if self.app_env == "cloud":
            if self.auth_mode != "firebase":
                raise ValueError("cloud environments require AUTH_MODE=firebase")
            if self.object_storage_backend != "gcs":
                raise ValueError("cloud environments require OBJECT_STORAGE_BACKEND=gcs")
            if self.local_principal_id is not None:
                raise ValueError("LOCAL_PRINCIPAL_ID is forbidden in cloud environments")
            if not self.gcp_project_id or not self.gcs_bucket:
                raise ValueError("GCP_PROJECT_ID and GCS_BUCKET are required in cloud environments")
            if self.cloud_max_instances is None or self.database_connection_budget is None:
                raise ValueError(
                    "CLOUD_MAX_INSTANCES and DATABASE_CONNECTION_BUDGET are required in cloud environments"
                )
            # Cloud Run can scale the new revision alongside the previous one.
            configured_connections = (
                2
                * self.cloud_max_instances
                * (self.database_pool_size + self.database_max_overflow)
            )
            if configured_connections > self.database_connection_budget:
                raise ValueError("per-instance database pools exceed DATABASE_CONNECTION_BUDGET")
            validate_cloud_database_url(self.database_url, direct=False)
        elif self.object_storage_backend != "local":
            raise ValueError("GCS object storage is available only in cloud environments")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
