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
.venv/bin/alembic upgrade head
uvicorn health_api.main:app --reload --app-dir services/api/src --host 127.0.0.1
```

In another terminal:

```bash
curl --fail http://127.0.0.1:8000/healthz
EXPO_PUBLIC_API_URL=http://127.0.0.1:8000 pnpm mobile:start
```

The shell uses Expo Go; it does not require an already-built development client. Use a compatible Expo Go simulator/device installation. `pnpm --filter @personal-health/mobile ios` builds the native shell locally if Xcode is installed. Phase 8 will introduce a development build for HealthKit. A Metro bundle check alone does not verify rendering on a device.

`EXPO_PUBLIC_API_URL` is compiled into the mobile app and may contain only the API address, never credentials or principal IDs. The default is `http://127.0.0.1:8000` for the local iOS simulator. For an Android emulator use `http://10.0.2.2:8000`; for a physical device, use an approved secure endpoint reachable on a private network and configure the local API/network accordingly. Do not expose this unauthenticated local-dev API to the public internet. Rebuild/restart Metro after changing the variable.

After the Python environment and API dependencies are ready, export OpenAPI and build the generated TypeScript client with `pnpm --filter @personal-health/api-client generate`. This performs no database request. Check generated source with `pnpm --filter @personal-health/api-client typecheck`; CI also regenerates the tracked artifacts and fails on drift.

`/healthz` is process liveness only: it requires no database, identity, objects, or AI service. Phase 1 loads the server-only settings in `.env` and adds owner-scoped Profile routes. Protected routes use the one `LOCAL_PRINCIPAL_ID` configured by the server; when it is absent, they return 401. `AUTH_MODE=dev` is accepted only in local/test settings, and the local principal is not real internet authentication. Never send owner IDs in a body/header or copy server environment variables into Expo public variables. Mobile requests use a separately configured public API URL; on a physical device, `localhost` is the phone itself. Keep development auth/API access private when allowing LAN access.

Profile requests are limited to 65,536 bytes and errors do not include submitted values. Responses include a server-generated `X-Request-ID`. Lists are owner/filter/as-of scoped with a 100-item maximum; preserve the returned `as_of` when following its cursor. Unknown values use explicit `null` in the required typed payload value; `false` and `0` remain known values.

## Migrations and database tests

Alembic owns all schema changes. The API never creates tables automatically. After bootstrap, apply and inspect the current schema with:

```bash
.venv/bin/alembic upgrade head
.venv/bin/alembic current
.venv/bin/alembic check
```

Persistence tests use real PostgreSQL and truncate their target database between tests. Create a separate disposable test database and provide its URL explicitly:

```bash
docker compose exec -T postgres createdb -U health health_test
TEST_DATABASE_URL=postgresql+psycopg://health:health@127.0.0.1:5432/health_test \
  PYTHONPATH=services/api/src pytest -c services/api/pyproject.toml services/api/tests
```

The test fixture refuses databases whose name does not include `test` or `phase1`. It automatically applies Alembic migrations and truncates the six Phase 1 tables. Never use personal data in this database. `alembic downgrade base` is destructive and belongs only on a disposable test database.

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

The Phase 1 API tests require `TEST_DATABASE_URL`; without it, PostgreSQL integration cases are skipped. CI provisions its own disposable PostgreSQL service. The generated client and Profile value model have behavioral Vitest tests; a test-only React DOM render checks accessible labels and opt-in defaults in the native Profile form. It does not verify interactive behavior. Device execution, create/edit/archive/history walkthrough, keyboard behavior, and assistive-technology accessibility remain manual checks on an equipped host.

Frontend resolutions are in `pnpm-lock.yaml`; install with `--frozen-lockfile`. API runtime/dev resolutions for the tested Python 3.12 macOS/Linux baseline are in `services/api/requirements-dev.lock`, consumed as pip constraints. This is not a platform-independent Python lock; test/regenerate deliberately when changing Python/platform or dependencies. Build tooling is separately pinned in `pyproject.toml`. Optional lock regeneration uses uv:

```bash
uv pip compile services/api/pyproject.toml --extra dev --python .venv/bin/python --output-file services/api/requirements-dev.lock
```

Update manifests and locks together, rerun checks, and record compatibility evidence. Routine development requires no cloud. `packages/domain`, `packages/design-tokens`, and `packages/shared` are documentation reservations, not importable packages. `packages/api-client` becomes a generated OpenAPI client during Phase 1. FastAPI is the authoritative contract source; do not add handwritten duplicate transport DTOs.

Known upstream dependency advisories and their source-use review are recorded in the [Phase 0 review](handoff/phase-0-review.md). Run `pnpm audit --prod` on dependency changes; a passing scaffold/type/bundle check is not a security-clean release claim. Resolve reachable Router deep-link issues before exposing a product to untrusted links.
