# Phase 8 local implementation evidence

Updated October 7, 2026. This record describes the local normalized-import
foundation and the checks run for it. **Phase 8 is not fully verified or
device-enabled.** Native HealthKit reads, permission semantics, platform
aggregation, actual deletion delivery, PostgreSQL transaction behavior, and
the P8.5 device matrix remain open. A mock-only result does not satisfy the
phase acceptance criteria.

## Delivered locally

- Added authenticated, owner-scoped batch, receipt, status, and aggregate
  preference routes. A batch contains one resource type and no more than 200
  total entry/tombstone changes. The batch route is limited to 1 MiB.
- The server computes a content hash, stores a compact owner-scoped receipt,
  and applies canonical Event/Observation writes in the same transaction.
  Low-frequency identities dedupe by owner/platform/type/source UUID across
  installations. Date-only step/heart-rate aggregates are installation,
  local-date, timezone, and policy scoped.
- Added a source preference for steps and heart-rate summaries. Today and
  analytics select one installation's aggregate for each type and do not sum
  device totals. Changing the selection invalidates analytics and starts a new
  Today snapshot boundary so existing paging cursors cannot mix selections.
- Imports begin device-sourced and `unconfirmed`; AI-use and cross-domain
  permissions stay off. A deliberate edit changes current provenance to
  manual/user-confirmed. Later source changes do not overwrite that correction.
  A tombstone archives only an unconfirmed device row and keeps its identity
  against a repeat read.
- Added normalized mobile mappers for workouts, sleep, steps, weight, resting
  heart rate, and a daily heart-rate summary. Sleep stage and heart-rate
  min/max/count/coverage use strict allowlisted metadata. Raw samples, routes,
  and high-frequency heart-rate arrays are not part of the transport.
- Added SecureStore-backed per-account/type consent and bounded initial
  lookback settings (30 days by default, maximum 90), plus an account/type/
  installation/policy-scoped opaque checkpoint. The coordinator writes a
  checkpoint only after an API acknowledgement and reports when secure
  checkpoint persistence fails after acknowledgement.
- Today displays device-imported/unconfirmed origin, manual-correction origin,
  and health-rate-summary coverage where available. Insights uses the new
  metrics through the existing metric catalog and keeps the Phase 7 coverage
  and exact-revision evidence behavior.

## Mappings and retention

| Health type        | Local normalized representation                                                           | What the server accepts                                                                        |
| ------------------ | ----------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| Workouts           | Exercise Event v1 with exact start and either end or explicit duration; optional distance | Source UUID and supported Event fields; no route/location series                               |
| Sleep              | Sleep Event v1 with exact interval                                                        | Source UUID and optional allowlisted stage metadata; no raw HealthKit object                   |
| Steps              | Date-only Exercise Observation using nonnegative integer `StepCountValueV1`               | Local date, timezone, count, source installation, and aggregation method version               |
| Weight             | Measurement Observation v1                                                                | Exact time, source UUID, value, and original kg/lb unit                                        |
| Resting heart rate | Measurement Observation v1 in BPM                                                         | Exact time and source UUID; no derived diagnosis                                               |
| Heart-rate summary | Date-only Measurement Observation v1 with mean BPM                                        | Mean plus bounded min/max/count/coverage and aggregation method version; no underlying samples |

The sleep stage remains envelope metadata rather than a new Event payload
version. A future typed stage or coverage payload must receive a new schema
version and migration policy. The client is a reporter of device data; the
server does not treat an installation ID as proof that Apple Health produced a
sample.

## Contract and persistence

- OpenAPI source: `services/api/src/health_api/api/healthkit_imports.py` and
  `health_api.domain.healthkit_imports`.
- Generated artifacts: `contracts/openapi/openapi.json` and
  `packages/api-client/src/generated.ts`.
- Alembic revision `c8d9e0f1a2b3` is the single head after
  `f7c8d9e0a1b2`. It adds batch receipts, import identities, source
  preferences, and the additive Observation metric/unit checks. Downgrade
  refuses while receipts or import identities exist.
- Receipt data contains IDs, content hash, policy, timestamp, and change
  counts. Server-side anchors and uploaded sample bodies are not retained.
- Source selection changes stale dependent analytical artifacts in the same
  owner transaction. Imported create/update/archive paths reuse daily history
  and analytics invalidation.

## Native, permission, and device status

The iOS capability reports `native_adapter_unavailable`; Android and web report
`unsupported_platform`. The settings screen is explicit that it does not
request Apple permissions or start a sync. No HealthKit native package,
HealthKit entitlement, or HealthKit usage-description strings are configured.
The current host's active developer path is
`/Library/Developer/CommandLineTools`; `xcodebuild -version` reports that full
Xcode is required. There was no HealthKit-capable test device in this run.

Expo native modules require a development build for custom native code; the
current app still uses Expo Go and has no HealthKit module. See [Expo
development builds](https://docs.expo.dev/develop/development-builds/use-development-builds/).
Apple's HealthKit store API controls read authorization and query behavior; an
empty query is not treated here as proof of denied permission or absent health
data. See [Apple HKHealthStore](https://developer.apple.com/documentation/healthkit/hkhealthstore).

Consequently, no native type is live-enabled. The mapper/coordinator fixtures
prove local serialization and acknowledgement ordering only; they do not prove
entitlements, permission reporting, no-data behavior, platform aggregation,
anchor reset, delete/revoke delivery, background behavior, or App Store
approval. P8.1 native compatibility, P8.2 platform reads, and P8.5 device
verification remain open. The secure lookback and consent settings are not yet
connected to a HealthKit query because no query adapter is installed.

## Checks run

| Check                                                                                                 | Result                                   | Limit                                                                                                               |
| ----------------------------------------------------------------------------------------------------- | ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| Python Ruff checks and formatting on changed API/domain/application/persistence/tests/migration files | Passed                                   | Focused changed-file scope                                                                                          |
| Python `compileall` on API source, Phase 8 tests, and migration                                       | Passed                                   | Syntax/bytecode only                                                                                                |
| Focused HealthKit API contract and route tests                                                        | 4 passed, 3 skipped                      | PostgreSQL-backed route cases require a disposable `TEST_DATABASE_URL`; none was configured                         |
| Focused Python mypy check                                                                             | Passed                                   | Four Phase 8 source/test files                                                                                      |
| Mobile TypeScript `tsc --noEmit`                                                                      | Passed                                   | Static typing only                                                                                                  |
| Mobile ESLint on changed app and test files                                                           | Passed                                   | No errors or warnings                                                                                               |
| API client TypeScript contract check                                                                  | Passed                                   | Generated contract typing only                                                                                      |
| Mobile Vitest (`daily-model`, HealthKit coordinator, HealthKit mapping)                               | 22 passed                                | Mocks do not exercise native APIs or PostgreSQL                                                                     |
| Expo iOS JavaScript export                                                                            | Passed                                   | Bundles JavaScript only; does not compile a native iOS app                                                          |
| `alembic heads`                                                                                       | `c8d9e0f1a2b3`                           | Reports the repository revision graph only                                                                          |
| `alembic upgrade head --sql`                                                                          | Passed                                   | Offline SQL generation; no live migration was applied                                                               |
| OpenAPI export and generated-client scripts                                                           | Passed via direct Python/Node invocation | The installed pnpm is 11.19.0; workspace requires pnpm 9, so its `pnpm --filter ... generate` wrapper could not run |
| Prettier check on changed sources and documentation                                                   | Passed                                   | Formatting only                                                                                                     |
| Relative Markdown links in changed documentation                                                      | 68 checked, 0 broken                     | Existence check; does not validate external links                                                                   |
| `xcodebuild -version`                                                                                 | Unavailable                              | Active developer path is Command Line Tools, not full Xcode                                                         |

## Phase 9 erasure requirements

Owner erasure must remove `healthkit_import_batches`,
`healthkit_import_identities`, and `healthkit_source_preferences` with canonical
health rows; the mobile erasure/sign-out workflow must delete that account's
HealthKit consent and secure checkpoints. Deletion must prevent automatic
re-import until the owner grants fresh consent. A device-only sign-out must
not delete server history, and turning off a type must stop future reads while
leaving already imported history intact unless the user explicitly removes it.
