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
curl --fail http://127.0.0.1:8000/readyz
EXPO_PUBLIC_API_URL=http://127.0.0.1:8000 pnpm mobile:start
```

The shell uses Expo Go; it does not require an already-built development client. Use a compatible Expo Go simulator/device installation. `pnpm --filter @personal-health/mobile ios` builds the native shell locally if Xcode is installed. The current Phase 8 implementation does not install a HealthKit native module or enable permissions; HealthKit settings remain informational until a compatible development build and native adapter are verified. A Metro bundle check alone does not verify rendering or HealthKit behavior on a device.

`EXPO_PUBLIC_API_URL` is compiled into the mobile app and may contain only the API address, never credentials or principal IDs. The default is `http://127.0.0.1:8000` for the local iOS simulator. For an Android emulator use `http://10.0.2.2:8000`; for a physical device, use an approved secure endpoint reachable on a private network and configure the local API/network accordingly. Do not expose this unauthenticated local-dev API to the public internet. Rebuild/restart Metro after changing the variable.

After the Python environment and API dependencies are ready, export OpenAPI and build the generated TypeScript client with `pnpm --filter @personal-health/api-client generate`. This performs no database request. Check generated source with `pnpm --filter @personal-health/api-client typecheck`; CI also regenerates the tracked artifacts and fails on drift.

`/healthz` is process liveness only: it requires no database, identity, objects, or AI service. `/readyz` checks the configured database connection with a read-only `SELECT 1` and returns only `{"status":"ok"}` or a generic 503 `{"status":"unavailable"}`. Run it after PostgreSQL is started and migrations are applied. Local settings use `APP_ENV=local`, `AUTH_MODE=dev`, `OBJECT_STORAGE_BACKEND=local`, and the one server-side `LOCAL_PRINCIPAL_ID`. Protected routes return 401 when that ID is absent. This identity is for private local development and is not internet authentication. The API uses a bounded SQLAlchemy pool and stores synthetic local objects under `.data/objects`; that directory is ignored by Git.

Cloud mode requires `APP_ENV=cloud`, `AUTH_MODE=firebase`, a Firebase project ID, GCP project and private GCS bucket identifiers, an explicit Cloud Run instance count and database connection budget, and a pooled Neon `DATABASE_URL` with `sslmode=verify-full`. The Cloud Run service receives database credentials from Secret Manager through its runtime identity. A release job uses the separate direct Neon URL as `MIGRATION_DATABASE_URL`; schema changes never run at API startup. Do not copy any server variables into Expo public variables. `.env.example` contains only local values; cloud configuration and secret names are listed in the [Phase 3 cloud release runbook](../infra/gcp/README.md).

When `EXPO_PUBLIC_AUTH_MODE=firebase`, the mobile app uses Firebase Authentication with persisted React Native SDK state, email/password sign-in, ID-token refresh and sign-out. The public Firebase app config (`EXPO_PUBLIC_FIREBASE_*`) and `EXPO_PUBLIC_API_URL` are build-time values, not secrets. Until the project details are supplied, keep `EXPO_PUBLIC_AUTH_MODE=dev` for local development. On a physical device, `localhost` is the phone itself; keep the local API and development auth on a private network.

Firebase mode additionally requires `EXPO_PUBLIC_FIREBASE_API_KEY`, `EXPO_PUBLIC_FIREBASE_AUTH_DOMAIN`, `EXPO_PUBLIC_FIREBASE_PROJECT_ID` and `EXPO_PUBLIC_FIREBASE_APP_ID`. These values identify the client app and are not authentication credentials. Firebase refresh tokens are persisted by the SDK through Expo SecureStore. The API obtains ownership only from a verified bearer ID token and the additive provider-identity mapping; it never trusts a client-supplied owner ID or merges identities by email.

Most request bodies are limited to 65,536 bytes. The normalized HealthKit batch route is limited to 1,048,576 bytes and 200 total changes per request. Errors do not include submitted health values. Responses echo a safe ASCII `X-Request-ID` of at most 64 characters; otherwise the server supplies a UUID. Request events are emitted as JSON lines with severity, request ID, method, route template, status, and duration. Body-limit rejections also include the configured limit and a fixed reason. Logs exclude query strings, other headers, bodies, health values, and raw exception details. Lists are owner/filter/as-of scoped with a 100-item maximum; preserve the returned `as_of` when following its cursor. Unknown values use explicit `null` in the required typed payload value; `false` and `0` remain known values.

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

The API persistence tests require `TEST_DATABASE_URL`; without it, PostgreSQL integration cases are skipped. CI provisions PostgreSQL 17 and the session fixture upgrades Alembic to head before running the API suite. This automates PostgreSQL migration and API regression coverage for tests in that suite; it does not establish Neon parity or production behavior. Do not treat SQLite as a substitute for PostgreSQL transaction, migration, uniqueness or query behavior. The generated client and Profile value model have behavioral Vitest tests; a test-only React DOM render checks accessible labels and opt-in defaults in the native Profile form. It does not verify interactive behavior. Device execution, create/edit/archive/history walkthrough, keyboard behavior, and assistive-technology accessibility remain manual checks on an equipped host.

CI also checks Terraform formatting and schema validation with backend initialization disabled, and builds the exact production API Dockerfile without pushing the image. These checks need no GCP credentials and do not deploy or establish live IAM, database, storage, or Cloud Run behavior.

Frontend resolutions are in `pnpm-lock.yaml`; use pinned pnpm **9.15.0** (for example `corepack pnpm@9.15.0`) and install with `--frozen-lockfile`. The checked-in `requirements-dev.lock` pins the Python 3.12 development/test environment as pip constraints; `requirements-runtime.lock` pins only the production dependency closure with hashes for the locked container install. Regenerate both deliberately when changing dependencies or Python/platform. Build tooling is separately pinned in `pyproject.toml`. Lock regeneration uses uv:

```bash
uv pip compile services/api/pyproject.toml --extra dev --python .venv/bin/python --output-file services/api/requirements-dev.lock
uv pip compile services/api/pyproject.toml --python .venv/bin/python --generate-hashes --output-file services/api/requirements-runtime.lock
```

Update manifests and locks together, rerun checks, and record compatibility evidence. Routine development requires no cloud. `packages/domain`, `packages/design-tokens`, and `packages/shared` are documentation reservations, not importable packages. `packages/api-client` becomes a generated OpenAPI client during Phase 1. FastAPI is the authoritative contract source; do not add handwritten duplicate transport DTOs.

Known upstream dependency advisories and their source-use review are recorded in the [Phase 0 review](implementation/evidence/phase-0-review.md). Run `pnpm audit --prod` on dependency changes; a passing scaffold/type/bundle check is not a security-clean release claim. Resolve reachable Router deep-link issues before exposing a product to untrusted links.
