from __future__ import annotations

import os
from logging.config import fileConfig
from typing import cast

from alembic import context
from health_api.config.settings import get_settings
from health_api.config.settings import migration_database_url as resolve_migration_database_url
from health_api.persistence.models import Base
from sqlalchemy import Connection, engine_from_config, pool

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def migration_database_url() -> str:
    direct_url = os.environ.get("MIGRATION_DATABASE_URL")
    app_env = os.environ.get("APP_ENV", "local")
    if app_env.lower() == "cloud":
        return resolve_migration_database_url(app_env, direct_url, None)
    local_url = get_settings().database_url.get_secret_value()
    return resolve_migration_database_url(app_env, direct_url, local_url)


def run_migrations_offline() -> None:
    context.configure(
        url=migration_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    injected_connection = config.attributes.get("connection")
    if injected_connection is not None:
        connection = cast(Connection, injected_connection)
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
        return

    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = migration_database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        echo=False,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
