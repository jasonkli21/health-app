# Local development

Run commands from the repository root unless stated otherwise. Tested baseline: Python 3.12, Node >=22.13, pnpm **9.15.0**, PostgreSQL 17. Install Node and the pinned pnpm (for example with Corepack); do not use an arbitrary global pnpm major. Docker Compose is required for the documented database workflow. iOS execution additionally requires compatible Xcode/iOS tooling; consult the [Expo SDK 57 compatibility table](https://docs.expo.dev/versions/v57.0.0/).

## Bootstrap

```bash
cp .env.example .env
docker compose up -d postgres
docker compose ps
pnpm install --frozen-lockfile
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -c services/api/requirements-dev.lock -e 'services/api[dev]'
uvicorn health_api.main:app --reload --app-dir services/api/src --host 127.0.0.1
```

In another terminal:

```bash
curl --fail http://127.0.0.1:8000/healthz
pnpm mobile:start
```

The shell uses Expo Go; it does not require an already-built development client. Use a compatible Expo Go simulator/device installation. `pnpm --filter @personal-health/mobile ios` builds the native shell locally if Xcode is installed. Phase 8 will introduce a development build for HealthKit. A Metro bundle check alone does not verify rendering on a device.

`/healthz` is process liveness only: it requires no database, identity, objects, or AI service. There are no domain routes, migrations, settings loader, or mobile API calls in Phase 0. `.env.example` records **planned server settings**; the current shell does not consume them. Do not copy server environment variables into Expo public variables. Once mobile calls exist in Phase 1, document its public API URL separately, including physical-device networking; localhost on a phone is the phone itself. Keep development auth/API access private when allowing LAN access.

The local database binds to loopback and uses disposable development credentials. It must never be exposed publicly or reused for cloud. `docker compose stop` preserves its volume. `docker compose down` removes containers but preserves data; removing the named volume is destructive and should be deliberate.

## Foundation checks

With the virtual environment active:

```bash
python scripts/verify_scaffold.py
PYTHONPYCACHEPREFIX=/tmp/personal-health-pycache python -m compileall -q services/api/src scripts
pytest -c services/api/pyproject.toml services/api/tests
ruff check --config services/api/pyproject.toml services/api/src services/api/tests scripts
ruff format --check --config services/api/pyproject.toml services/api/src services/api/tests scripts
mypy --config-file services/api/pyproject.toml services/api/src scripts
pnpm format:check
pnpm mobile:lint
pnpm mobile:typecheck
pnpm mobile:test
pnpm --filter @personal-health/mobile exec expo install --check
pnpm --filter @personal-health/mobile exec expo export --platform ios --output-dir /tmp/personal-health-ios-bundle
```

The mobile test hook currently passes with **no tests**; it is not coverage. Vitest is reserved for pure TypeScript; Phase 1 must establish a React Native component test runner and real tests in `apps/mobile/tests/`. The API smoke test verifies liveness. All product verification is still future work. CI runs the foundation checks except device execution/Metro export and database startup.

Frontend resolutions are in `pnpm-lock.yaml`; install with `--frozen-lockfile`. API runtime/dev resolutions for the tested Python 3.12 macOS/Linux baseline are in `services/api/requirements-dev.lock`, consumed as pip constraints. This is not a platform-independent Python lock; test/regenerate deliberately when changing Python/platform or dependencies. Build tooling is separately pinned in `pyproject.toml`. Optional lock regeneration uses uv:

```bash
uv pip compile services/api/pyproject.toml --extra dev --python .venv/bin/python --output-file services/api/requirements-dev.lock
```

Update manifests and locks together, rerun checks, and record compatibility evidence. Routine development requires no cloud. `packages/domain`, `packages/design-tokens`, and `packages/shared` are documentation reservations, not importable packages. `packages/api-client` is a workspace placeholder; `generate` deliberately fails until Phase 1 adds actual OpenAPI export/client generation. FastAPI is the authoritative contract source; no handwritten duplicate DTOs.

Known upstream dependency advisories and their source-use review are recorded in the [Phase 0 review](handoff/phase-0-review.md). Run `pnpm audit --prod` on dependency changes; a passing scaffold/type/bundle check is not a security-clean release claim. Resolve reachable Router deep-link issues before exposing a product to untrusted links.
