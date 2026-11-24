#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
root=$(pwd)
pas=$(cd ../../pas && pwd)
export PAS_PYTHON="${PAS_PYTHON:-/tmp/pas-dispatch-venv/bin/python}"
health_python="${HEALTH_PYTHON:-/tmp/health-step2-venv/bin/python}"
export HEALTH_PAIRED_DSN="${HEALTH_PAIRED_DSN:-postgresql+psycopg:///health_paired_test?host=/tmp/paired-health-pg.socket&port=55486}"
export PAS_PAIRED_DSN="${PAS_PAIRED_DSN:-postgresql://127.0.0.1/pas_health_paired_test?host=/tmp/paired-health-pg.socket&port=55486}"
export PYTHONPATH="$root/../services/api/src:$pas/backend/tests/app_context_support"
exec "$health_python" -sB "$root/health_worker.py" "$@"
