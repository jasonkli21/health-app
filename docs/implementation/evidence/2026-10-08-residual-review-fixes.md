# Residual review fixes — October 8, 2026

This record closes the local implementation work for the residual review against
Health HEAD `3658d5094dbd2ff66a47aee94dace0158abbc772`. The final fix commit SHA
is included in the task completion record; a content-addressed commit cannot
embed its own final SHA in this file.

## Findings addressed

- **R1 — Assistant request ownership:** search, preview, and message requests
  use explicit operation leases. Query/type/scope changes and focus transitions
  release stale busy state; stale results and errors are rejected, and an old
  completion cannot release a newer request.
- **R2 — Proposal pagination:** proposal page state has a stable coordinator;
  page cursors do not change the focus callback. Deferred controller tests
  verify one initial request, explicit next-cursor loading, retained pages,
  stable status loading, and a still-current preview.
- **R3 — Readiness bounds:** pooled idle connections limit pre-ping work, pool
  checkout and connection establishment are capped at one second, and `/readyz`
  applies a transaction-local one-second timeout to its read-only probe. The
  existing five-second Cloud Run probe configuration remains unchanged.
- **R4 — Request logging:** Alembic logging setup preserves existing loggers.
  A PostgreSQL-backed regression runs migration setup and then checks
  correlated, structured normal/error/body-limit request events and privacy
  exclusions in the same process.
- **R5 — Static CI gates:** strict mypy, Ruff, and repository Prettier checks
  pass without broad suppressions. The migration-index expression typing stays
  narrow; no export/erasure SQL or transaction behavior was changed.

No test assertions were removed, no lint/type rules were disabled, no
dependency versions or OpenAPI contracts changed, and no Personal AI files were
modified.

## Local verification

Commands ran in the repository unless a working directory is shown.

| Command                                                                                                                                                                                                              | Result                                                                                                                        |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `.venv/bin/python scripts/verify_scaffold.py`                                                                                                                                                                        | Passed.                                                                                                                       |
| `env -u TEST_DATABASE_URL APP_ENV=test .venv/bin/pytest -c services/api/pyproject.toml services/api/tests -q`                                                                                                        | 172 passed, 71 skipped, 1 existing Starlette deprecation warning. All 71 skips require `TEST_DATABASE_URL`.                   |
| `.venv/bin/ruff check --config services/api/pyproject.toml services/api/src services/api/tests services/api/scripts scripts`                                                                                         | Passed.                                                                                                                       |
| `.venv/bin/ruff format --check --config services/api/pyproject.toml services/api/src services/api/tests services/api/scripts scripts`                                                                                | Passed; 98 files already formatted.                                                                                           |
| `.venv/bin/mypy --config-file services/api/pyproject.toml services/api/src services/api/scripts scripts`                                                                                                             | Passed; 63 source files.                                                                                                      |
| `./node_modules/.bin/prettier --check .`                                                                                                                                                                             | Passed; all matched files formatted.                                                                                          |
| `.venv/bin/python services/api/scripts/export_openapi.py && node packages/api-client/scripts/generate-client.mjs`                                                                                                    | Passed.                                                                                                                       |
| `git diff --exit-code -- contracts/openapi/openapi.json packages/api-client/src/generated.ts`                                                                                                                        | Passed; generated artifacts had no drift.                                                                                     |
| `cd packages/api-client && ../../apps/mobile/node_modules/.bin/tsc --noEmit --strict --skipLibCheck --target ES2022 --module ESNext --moduleResolution Bundler src/index.ts`                                         | Passed.                                                                                                                       |
| From `apps/mobile`: `./node_modules/.bin/vitest run --passWithNoTests`                                                                                                                                               | Passed; 32 files and 152 tests. Includes deferred controller, page, search invalidation, and operation ownership regressions. |
| From `apps/mobile`: `./node_modules/.bin/tsc --noEmit`                                                                                                                                                               | Passed.                                                                                                                       |
| From `apps/mobile`: `./node_modules/.bin/eslint .`                                                                                                                                                                   | Passed with 0 errors and 6 existing warnings in `profile-create-session.test.tsx` and `session-review.test.ts`.               |
| From `apps/mobile`: `EXPO_NO_TELEMETRY=1 __UNSAFE_EXPO_HOME_DIRECTORY=/private/tmp/health-app-expo-home ./node_modules/.bin/expo export --platform ios --output-dir /private/tmp/personal-health-residual-fixes-ios` | Passed; iOS JavaScript bundle exported.                                                                                       |
| `.venv/bin/alembic heads`                                                                                                                                                                                            | Passed; one head, `20261007b1c2`.                                                                                             |
| `git diff --check`                                                                                                                                                                                                   | Passed before commit.                                                                                                         |

The workspace has global pnpm `11.25.0`, while the repository pins
`pnpm@9.15.0`; no compatible pnpm 9 executable was available. The equivalent
installed local binaries were used for Prettier, Vitest, TypeScript, ESLint,
the Expo export, and API-client generation. No package-manager or dependency
version changes were made.

## Unverified gates

No `TEST_DATABASE_URL` was available. An isolated PostgreSQL 17.11 cluster
could not be started because the host denied or failed shared-memory allocation
(`Operation not permitted` and `No space left on device`). Therefore the
PostgreSQL-backed tests were skipped, including the new migration-plus-request
logging regression, readiness pool-exhaustion/recovery and slow-query timeout
regressions, and migration/model agreement. The 172 passing API tests do not
establish PostgreSQL behavior.

`terraform` and `docker` executables were not installed, so Terraform format,
provider initialization/validation, and the production Docker build remain
unverified. No Terraform probe configuration changed. Live cloud, Neon,
Firebase, GCS, Cloud Run, native device, accessibility, and Personal AI gates
remain external and unverified.

## Confirmatory verification follow-up

The independent verification pass found that the committed controller tests
did not exercise an in-flight search or preview across blur/refocus. Two
controller-level deferred-response regressions were added for those paths;
both verify that stale results stay excluded and an older completion cannot
clear a newer request's busy state.

On the follow-up working tree, `vitest run --passWithNoTests` passed 32 files
and 154 tests; mobile TypeScript passed, and ESLint reported zero errors with
the same six existing warnings listed above. Prettier, scaffold verification,
OpenAPI/client generation after formatting, generated-artifact drift, API
client typecheck, Ruff, Ruff format, and mypy passed. Expo iOS export also
passed as a JavaScript bundle check only. API tests without a database passed
172 tests and skipped the 71 PostgreSQL cases.

A second disposable database startup attempt with the installed PostgreSQL
16.15 binaries failed during `initdb` because the host could not allocate
shared memory. A retry with the installed PostgreSQL 17 binaries and an
`mmap` dynamic shared-memory setting failed at the same bootstrap allocation.
The R3/R4 database regressions, migration/model agreement, and PostgreSQL 17
full-suite result therefore remain unverified. Terraform and Docker remain
unavailable, so provider validation and the production image build remain
unverified.
