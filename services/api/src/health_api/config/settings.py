"""Server-only configuration with a local-only development identity guard."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from health_api.domain.schemas import validate_iana_timezone


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["local", "test"] = "local"
    database_url: str = Field(
        default="postgresql+psycopg://health:health@127.0.0.1:5432/health", min_length=1
    )
    auth_mode: Literal["dev"] = "dev"
    local_principal_id: UUID | None = None
    local_principal_timezone: str = "America/Los_Angeles"
    api_base_url: str = "http://127.0.0.1:8000"

    @field_validator("local_principal_timezone")
    @classmethod
    def timezone_must_be_iana(cls, value: str) -> str:
        return validate_iana_timezone(value)

    @model_validator(mode="after")
    def development_auth_is_local_only(self) -> Settings:
        if self.auth_mode == "dev" and self.app_env not in {"local", "test"}:
            raise ValueError("development authentication is allowed only in local or test mode")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
