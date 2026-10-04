# Phase 3 release evidence

**Checkpoint:** October 4, 2026. **Scope:** local implementation and offline
release artifacts only. No cloud project was selected, no service was
provisioned, and no cloud spend occurred.

## Completion status

P3.1–P3.3 are implemented and committed for local review. P3.4 has a Terraform
configuration, Cloud Build recipe, explicit image-build script and release
runbook, but its HCL was not formatted or validated and it was not applied.
P3.5 live identity, storage, database, rollout, rollback and cost acceptance
remains open. The implementation does not authorize Phase 4.

The Phase 2 PostgreSQL gate remains deferred under the user's explicit
instruction to proceed. The final local API run reports **77 passed and 41
skipped**. Forty skips are the carried Phase 2 PostgreSQL tests; the new
provider-identity first-login race test is the 41st PostgreSQL-dependent skip.
Alembic offline SQL generation is supplemental evidence only; it does not
replace PostgreSQL route/persistence tests, migration lifecycle or drift
checks, or query-plan measurements.

## Commit record and implementation

- `d041477 feat(config): add strict cloud settings and provider identity mapping`
  adds the local/test/cloud settings contract, bounded DB-pool configuration,
  verified issuer/subject mapping and additive provider identity migration.
- `95d7c3d feat(auth): verify Firebase identities and mobile sessions` adds
  Firebase Admin ID-token verification, a shared owner resolver for Profile
  and daily routes, explicit bearer security in OpenAPI, and mobile Firebase
  Auth sign-in/session restoration/refresh/sign-out behavior.
- `0708109 feat(storage): add bounded local and GCS adapters` adds local
  dirfd-relative no-follow storage, bounded private GCS operations, app-state
  wiring and the non-root container using the hashed runtime dependency lock.
- `c288982 infra(gcp): add explicit cloud release plan and runbook` adds
  required release inputs, service accounts, private bucket/IAM, separate
  migration Job, Cloud Run resource caps and the staged release/rollback
  runbook.

Cloud authentication accepts only verified Firebase issuer/subject identities;
the unique database mapping is never derived from email and never falls back
to a local principal. Firebase token verification checks revocation with a
bounded request timeout and in-flight limit. Invalid, expired, revoked,
disabled, missing or wrong-project credentials fail closed; verifier outages
return a sanitized 503. Every existing Profile and daily resource/history
route uses the same owner dependency.

The mobile app uses the actual Firebase JavaScript Auth SDK and Expo SecureStore
for persisted session state. It refreshes a token once after an API 401, expires
and clears rejected sessions, clears in-memory uncertain-create recovery state
on account changes and sign-out, and protects the existing routes until a
Firebase session is restored. Local development continues to use its
server-configured principal without Firebase. No product upload, AI, planning,
HealthKit or web functionality was added.

The local storage adapter uses UUID-only owner/object names, creates private
directories/files and uses no-follow descriptor-relative operations for each
configured-root path component. GCS calls use ADC, bounded object sizes,
timeouts, disabled retries and generation preconditions; the bucket resource
enforces uniform bucket-level access and public access prevention. Storage is
wired but has no product upload routes. Both adapters accept bounded in-memory
`bytes`; streaming upload behavior is deferred with the product upload flow.

The API image uses Python `3.12.14-slim-bookworm`, a `--require-hashes`
production requirements lock, UID/GID `10001`, one Uvicorn worker, the injected
`PORT`, and an eight-second graceful-shutdown limit. Migrations run only in a
separate Cloud Run Job using a direct Neon URL. Runtime pools reserve
`2 × max instances × (pool size + overflow)` to account for overlapping
revisions. No secret values, local objects or test fixtures are placed in the
image by the Dockerfile. These are source/configuration claims; the image was
not built or scanned on this host.

## Local verification

The Python environment is the repository `.venv` on Python 3.12.14. The API
suite and exact skip inventory were checked with:

```bash
.venv/bin/pytest -q -rs
```

Result: `77 passed, 41 skipped, 1 warning`. The warning is Starlette's
deprecation notice about `httpx` in `TestClient`. Every skip says
`PostgreSQL integration tests require TEST_DATABASE_URL`:

| Test file                                                  | Skipped | Gate                                          |
| ---------------------------------------------------------- | ------: | --------------------------------------------- |
| `services/api/tests/test_daily_api.py`                     |      12 | Carried Phase 2 PostgreSQL route checks       |
| `services/api/tests/test_daily_persistence.py`             |       6 | Carried Phase 2 PostgreSQL persistence checks |
| `services/api/tests/test_profile_api.py`                   |       9 | Carried Phase 2 PostgreSQL route checks       |
| `services/api/tests/test_profile_persistence.py`           |      13 | Carried Phase 2 PostgreSQL persistence checks |
| `services/api/tests/test_provider_identity_persistence.py` |       1 | New Phase 3 PostgreSQL first-login race       |
| **Total**                                                  |  **41** | **40 Phase 2 skips + 1 Phase 3 skip**         |

Python lint, formatting, type, scaffold and runtime-lock resolution checks:

```bash
.venv/bin/ruff check --config services/api/pyproject.toml services/api/src services/api/tests scripts migrations
.venv/bin/ruff format --check --config services/api/pyproject.toml services/api/src services/api/tests scripts
.venv/bin/mypy --config-file services/api/pyproject.toml services/api/src scripts
.venv/bin/python scripts/verify_scaffold.py
.venv/bin/python -m pip check
.venv/bin/python -m pip install --dry-run --require-hashes --no-deps -r services/api/requirements-runtime.lock
```

Results: Ruff passed; 43 files were already formatted; mypy reported no issues
in 24 source files; scaffold verification and `pip check` passed; the runtime
lock dry run resolved all 57 locked packages already present in `.venv`.
Python compileall also passed for `services/api/src`, `migrations` and
`scripts`.

The exact pnpm 9.15.0 frozen install succeeded after the local sandbox's first
network attempt failed DNS resolution. The successful retry used the bundled
Node 24 runtime and local pnpm store; it restored 862 packages with zero
downloads:

```bash
CI=true PATH="/Users/jasonkli/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/Users/jasonkli/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback:$PATH" \
  pnpm dlx pnpm@9.15.0 install --frozen-lockfile --ignore-scripts
```

Mobile validation used the same Node PATH and pinned pnpm command:

```bash
CI=true pnpm dlx pnpm@9.15.0 --filter @personal-health/mobile typecheck
CI=true pnpm dlx pnpm@9.15.0 --filter @personal-health/mobile test
CI=true pnpm dlx pnpm@9.15.0 --filter @personal-health/mobile lint
CI=true pnpm dlx pnpm@9.15.0 format:check
CI=true pnpm dlx pnpm@9.15.0 --filter @personal-health/api-client typecheck
```

Results: strict TypeScript passed, **60 mobile tests passed**, ESLint passed,
whole-repository Prettier passed after formatting one session-store file, and
generated API-client TypeScript passed. Expo produced an iOS export from 1,157
modules with a 2.9 MB Hermes bundle:

```bash
EXPO_NO_TELEMETRY=1 pnpm dlx pnpm@9.15.0 --filter @personal-health/mobile exec expo export --platform ios --output-dir /private/tmp/health-phase3-ios-export
```

OpenAPI was regenerated with the `.venv/bin` directory and bundled Node 24 on
`PATH`; `@personal-health/api-client` typecheck passed and regeneration left no
tracked diff. Offline Alembic SQL generation against a synthetic, non-routable
Neon-shaped URL emitted 283 lines and reached head `c3721f5a9a01`:

```bash
APP_ENV=cloud MIGRATION_DATABASE_URL='postgresql+psycopg://phase3:synthetic@ep-phase3.us-east-2.aws.neon.tech/health?sslmode=verify-full' \
  .venv/bin/alembic upgrade head --sql >/private/tmp/health-phase3-migration.sql
```

This confirms only that Alembic can render offline PostgreSQL SQL. It does not
verify the migration against a live PostgreSQL server or prove transactional
behavior, data compatibility, upgrade/downgrade/re-upgrade, drift or query
performance.

The deploy-script shell syntax check (`bash -n scripts/build_cloud_image.sh`)
passed; Ruby parsed `infra/gcp/cloudbuild.yaml`; calling the build script with
no arguments exited with its expected usage status `64` and did not invoke
`gcloud`. `git diff --check` passed.

## Deferred environment and release gates

No disposable PostgreSQL test database was available. Prior Phase 2 evidence
records `initdb` failing with shared-memory `ENOSPC`; Docker is unavailable as
well. No retries were made in this phase, and no unrelated cluster or shared
IPC resource was touched. Before release, restore a disposable PostgreSQL 16+
instance, set `TEST_DATABASE_URL`, run the full suite including all 41 skips,
exercise migrations on fresh and existing synthetic data, check Alembic/model
drift, and measure the Today query plans and latency. SQLite is not an
equivalent.

At this checkpoint `terraform`, `tofu`, `gcloud`, `docker` and `podman` were
not executable on the host. Terraform HCL was not formatted or validated, the
provider lock was not generated, and the image was not built/scanned/run. A
Python HCL parser was also unavailable; an attempt to install one could not
resolve `pypi.org` from the restricted network. Cloud Build YAML and shell
syntax checks do not substitute for Terraform validation.

Required owner-supplied release inputs remain pending: deployment GCP project,
Firebase Auth project, region, Neon pooled and direct endpoint secret IDs and
numeric Secret Manager versions, private GCS bucket name plus retention/
lifecycle decision, Artifact Registry repository and approved build identity,
Terraform state bucket and prefix, maximum instance count, database connection
budget, and approved spend budget. Secret values must be delivered through
Secret Manager only. No arbitrary project, account, region, bucket or budget
was selected; no secrets were requested or recorded. There are no real Firebase
test users or live API/bucket/DB endpoints for P3.5 validation.

CloudRun deployment, Firebase user and revocation flows, Neon TLS/pooling and
migration execution, GCS IAM/object round trip, startup/outage behavior,
connection counts, billing, log redaction, rollback and mobile device/keyboard/
accessibility behavior all remain live or manual release gates. Do not describe
P3.4 as deployed, P3.5 as complete, or Phase 4 as authorized.

## Official vendor references checked October 4, 2026

- Firebase's [Admin token verification guide](https://firebase.google.com/docs/auth/admin/verify-id-tokens)
  describes verifying client-SDK ID tokens on a backend. Its [session
  management guide](https://firebase.google.com/docs/auth/admin/manage-sessions)
  documents revocation checks and the additional Auth service lookup required
  for a stateless ID token. This informs the explicit timeout and fail-closed
  outage behavior; the hosted service has not been tested.
- The Firebase JS [Auth reference](https://firebase.google.com/docs/reference/js/auth)
  documents React Native auth persistence APIs. [Expo SecureStore](https://docs.expo.dev/versions/latest/sdk/securestore/)
  documents encrypted device key-value storage. Package integration compiled
  and bundled, but real device persistence and account switching remain manual
  checks.
- Neon documents [database endpoints](https://neon.com/docs/manage/endpoints/)
  and [connection pooling](https://neon.com/docs/connect/connection-pooling/).
  The implementation requires a pooled runtime URL and direct migration URL
  with verified TLS, but no Neon project, endpoint or plan limit was selected.
- The Cloud Run [container contract](https://docs.cloud.google.com/run/docs/container-contract)
  documents the injected container port and a 10-second SIGTERM shutdown
  window; its [concurrency guide](https://docs.cloud.google.com/run/docs/about-concurrency)
  documents per-instance request limits. The template uses one worker,
  concurrency 8 and an eight-second Uvicorn shutdown limit. This is a
  conservative configuration choice, not a measured capacity or cost result.
- Cloud Storage's [uniform bucket-level access guide](https://docs.cloud.google.com/storage/docs/uniform-bucket-level-access)
  documents ACL disablement in favor of IAM, and its [IAM role reference](https://docs.cloud.google.com/storage/docs/access-control/iam-roles)
  describes `roles/storage.objectUser` object operations. The IaC selects those
  controls but no live bucket policy has been inspected.
- The pinned Google provider's [Cloud Run v2 service resource](https://registry.terraform.io/providers/hashicorp/google/8.2.0/docs/resources/cloud_run_v2_service)
  is the resource reference for the reviewable Terraform source. Its provider
  configuration and schema have not been initialized or validated locally.
