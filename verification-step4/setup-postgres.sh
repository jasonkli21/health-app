#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
pg_bin="${PG_BIN:-/tmp/health-step2-venv/lib/python3.12/site-packages/pgserver/pginstall/bin}"
pg_data="${PAIRED_PG_DATA:-/tmp/paired-health-pg}"
pg_socket="${PAIRED_PG_SOCKET:-/tmp/paired-health-pg.socket}"
pg_port="${PAIRED_PG_PORT:-55486}"
health_python="${HEALTH_PYTHON:-/tmp/health-step2-venv/bin/python}"
mkdir -m 700 -p "$pg_socket"
"$pg_bin/initdb" -D "$pg_data" --auth=trust --no-locale -E UTF8
"$pg_bin/pg_ctl" -D "$pg_data" -o "-k $pg_socket -p $pg_port -c listen_addresses=''" \
    -l "$pg_data/server.log" start
"$pg_bin/createdb" -h "$pg_socket" -p "$pg_port" health_paired_test
"$pg_bin/createdb" -h "$pg_socket" -p "$pg_port" pas_health_paired_test
cd ..
export MIGRATION_DATABASE_URL="postgresql+psycopg:///health_paired_test?host=$pg_socket&port=$pg_port"
PYTHONPATH=services/api/src "$health_python" -m alembic upgrade head
