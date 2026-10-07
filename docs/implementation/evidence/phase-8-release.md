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

| Health type        | Local normalized representation                                                           | What the server accepts                                                                           |
| ------------------ | ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Workouts           | Exercise Event v1 with exact start and either end or explicit duration; optional distance | Source UUID and supported Event fields; no route/location series                                  |
| Sleep              | Sleep Event v1 with exact interval                                                        | Source UUID and optional allowlisted stage metadata; no raw HealthKit object                      |
| Steps              | Date-only Exercise Observation using bounded nonnegative integer `StepCountValueV1`       | Local date, timezone, count, source installation, aggregation method version, and source revision |
| Weight             | Measurement Observation v1                                                                | Exact time, source UUID, value, and original kg/lb unit                                           |
| Resting heart rate | Measurement Observation v1 in BPM                                                         | Exact time and source UUID; no derived diagnosis                                                  |
| Heart-rate summary | Date-only Measurement Observation v1 with mean BPM                                        | Mean plus bounded min/max/count/coverage and aggregation method version; no underlying samples    |

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
- Alembic revision `20261007a0b1` is the single head after
  `c8d9e0f1a2b3`. It adds aggregate source revisions, tombstone-only identity
  rows, user-archive protection, and step shape/range checks declared
  `NOT VALID`: PostgreSQL enforces them for new or updated rows without rejecting
  legacy step rows that predate the date-only and numeric-bound contract.
  Downgrade refuses when receipts, identity history, or source revisions would
  be lost.
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

## Independent-review follow-up

The follow-up fixes the findings in the [independent review](phase-8-independent-review.md)
without enabling native HealthKit. Sleep duration now partitions overlapping
intervals, prefers detailed stages over generic sleep, excludes `awake`, and
counts each instant once. Aggregate entries and tombstones carry bounded,
monotonic per-installation/type/local-day source revisions across timezone
variants; stale updates are ignored, sample tombstones are terminal, and a
newer aggregate revision can recompute a deleted day. Today, trends, and
consented Today summaries share the representative selection rules. Confirmed
manual corrections remain the day representative regardless of device
preference, while imported timeline rows remain visible independently from
selection.

Deletion-before-create is stored as an owner/type/source identity without a
fabricated health object. User archives are explicitly recorded and remain
inactive across source changes and deletions. The mobile coordinator encodes
SecureStore key components into the supported alphabet, binds sync work to the
current session epoch/type consent, serializes each scope, compares prepared
opaque anchors by equality, and recovers an acknowledged checkpoint before
accepting another batch in that scope. The public Observation contract bounds
step counts at `1e300` and requires date-only steps; imported workouts require
an end or duration, and low-frequency weight/resting-heart-rate imports are
exact instants. Today reads hold a shared owner lock through cursor validation
and snapshot loading; invalidated page cursors remain `422 invalid_cursor`.

OpenAPI and the generated TypeScript client include the source revision and
step contract. The generated-client script preserves object fields when
schemas combine them with `allOf` constraints. The migration also adds
database checks for new date-only, bounded step rows. Its downgrade refuses to
discard deletion identities or accepted source revisions.

### Follow-up checks

| Check                                            | Result                                           | Limit                                                                                                                         |
| ------------------------------------------------ | ------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------- |
| Changed API Python lint                          | Passed                                           | Ruff on changed service, schema, model, migration, and test files                                                             |
| Daily rollup and HealthKit import contract tests | 34 passed after review fixes                     | In-process domain/contract coverage; does not replace PostgreSQL integration                                                  |
| Focused API mypy                                 | Passed                                           | Four changed application/domain files                                                                                         |
| Mobile TypeScript check                          | Passed                                           | Generated client refreshed for this follow-up                                                                                 |
| Mobile Vitest suite                              | 115 passed                                       | Mocks do not exercise native SecureStore or HealthKit                                                                         |
| Changed mobile ESLint                            | Passed                                           | No warnings or errors                                                                                                         |
| PostgreSQL HealthKit API/race suite              | 7 skipped; `TEST_DATABASE_URL` is not configured | Database lifecycle/concurrency behavior remains an open acceptance gate; race coverage is checked in for PostgreSQL execution |
| Alembic/OpenAPI/generated-client checks          | Passed; `20261007a0b1` is the single head        | Offline SQL generation and client typing do not establish live database behavior                                              |
| Prettier, Markdown links, and whitespace checks  | Passed; 22 relative links checked                | Formatting/link existence only                                                                                                |

The native permission, aggregation, deletion, and device gates remain open.
The mobile checks verify local serialization and synchronization contracts
only.

## Phase 9 erasure requirements

Owner erasure must remove `healthkit_import_batches`,
`healthkit_import_identities`, and `healthkit_source_preferences` with canonical
health rows; the mobile erasure/sign-out workflow must delete that account's
HealthKit consent and secure checkpoints. Deletion must prevent automatic
re-import until the owner grants fresh consent. A device-only sign-out must
not delete server history, and turning off a type must stop future reads while
leaving already imported history intact unless the user explicitly removes it.
