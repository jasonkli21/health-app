# Phase 8 — Selective HealthKit integration

## Implementation-time reconciliation gate

**Status: planned. Dependencies: accepted Phases 1–7 with real evidence.** Read [Phase 8 roadmap](../implementation-plan.md#phase-8--healthkit), ADR 0005/mobile-native boundary, actual Event/Observation/source catalog, Today/analytics selection methods, cloud auth and generated client. Inspect Expo/RN/native-library compatibility and current Apple HealthKit APIs/entitlements/privacy/background requirements from official sources at execution time. Record drift and update material plan/ADR before code.

Existing homes: `apps/mobile/{app,src,tests}` and mobile manifest, API layers/tests, migrations/contracts and frontend package reservations. Native adapters/import schemas/cursors/build config below are **planned/provisional**. No HealthKit package or adapter exists in Phase 0; never import native code into api-client/domain/design-tokens/shared for hypothetical future web reuse.

## User outcome / scope

**Deliver:** optional, user-controlled first-wave import of workouts, sleep, steps, weight, resting heart rate and heart-rate summaries. Fine-grained type selection, source/provenance, selective retention, dedupe, correction/deletion processing, checkpoints and Today/Insights integration.

**Defer:** all other HealthKit types, write-back to HealthKit, raw high-frequency heart-rate/activity streams in cloud, other wearable/provider integrations, broad historical mirror, records/AI import interpretation/web. Manual app remains fully useful on unsupported device/Android, denied permissions and disabled integration. Background execution is best effort only; foreground sync is the initial correctness path.

## Native boundary and permission contract

Planned `apps/mobile/src/integrations/healthkit` contains capability/permission/query adapter and mapping. Feature UI depends on its small typed interface, not library calls throughout screens. Shared packages hold only generated import DTOs/frontend-safe formatting; no native HealthKit import/type in shared exports. The backend validates normalized import requests, not Apple SDK objects.

Select/pin the smallest maintained native library compatible with completed mobile SDK/RN and supported API surface; verify real iOS development build, entitlements/usage descriptions and behavior before committing to it. Move from Expo Go to a documented development build only here. Production distribution/Apple review/background delivery rules are external gates, not proven by Jest. HealthKit “no samples” may not distinguish denied reads from true empty data depending on actual SDK behavior: never claim permission granted/data absent from an empty query alone. Show authorized/requested/unknown/denied states only when observed API permits that distinction.

User selects supported types, bounded initial lookback (default30days/max90 per operation) and account-specific import consent before request. Permissions are device/platform state, Health sync enablement is per app owner/type. Signing in to a different app account does not silently import a previous account's health data; require fresh consent, isolate checkpoint keys and clear sensitive local query/cache state on logout. Never automatically send samples merely because platform permission remains. Turning sync off stops future reads/uploads and background tasks; previously imported rows remain unless user explicitly selects removal/deletion. No automatic AI-use permission: imports default restrictive inherited policy.

## Retention and normalization matrix

| First-wave type      | Cloud-retained normalized representation                                                                                                      | Raw retained locally / not uploaded                                               |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| Workouts             | Phase 2 exercise Event: source sample UUID, type/start/end and explicit duration/distance if provided; supported energy only if schema exists | Routes, location tracks, raw sensor streams excluded                              |
| Sleep                | Versioned sleep Event/segments with intervals and stage only where supported; preserve source/time and overlap-selection policy               | Original bounded batch held only until normalization/ack; no permanent raw mirror |
| Steps                | One daily device aggregate Observation with local date/zone, interval, count/unit and method/source summary                                   | Individual step samples stay in HealthKit                                         |
| Weight               | Low-frequency weight Observation, original unit/value/sample UUID/time                                                                        | No extra raw payload                                                              |
| Resting HR           | Low-frequency Observation or day summary based on actual HealthKit type semantics, unit beats/min and coverage                                | No inferred diagnosis                                                             |
| Heart rate summaries | Daily summary Observation (min/max/mean, sample count, interval/coverage and method version), only if valid samples available                 | Individual high-frequency heart-rate samples never leave mobile                   |

Phase 2 schemas may need additive versions/catalog entries for steps/resting-HR/HR-summary/sleep stages. Introduce typed import metadata/metric versions here with migration/client compatibility; do not pretend those metrics already exist. Health validates all normalized types/units/time/limits, source IDs/owner, content hash and aggregation method version. Native samples are **client-reported device data**, not cryptographically authenticated medical records; service cannot trust arbitrary mobile claims as independent verification. Provenance shows device-imported origin + `unconfirmed` confirmation status (distinct from AI pending proposal and user-confirmed fact). Consent to sync is not confirmation of each sample's medical accuracy.

Device source metadata contains minimal app/source bundle identifier/version and device label only when needed; no serial/identifying detail or raw sample metadata dump. Quantity conversion is deterministic, original supported unit retained. Workout/sleep intervals map using Phase 2 overlap rules; overlapping sleep sources must not simply add duration. Step/heart summaries use a documented, SDK-verified source-aware aggregation method. Prefer platform authoritative aggregation where its deduplication/source semantics are verified; otherwise select one ranked source per overlapping interval/day and expose coverage/conflicts. Do not sum independent providers' daily totals. Persist method/policy versions and source coverage, not every raw sample behind the aggregate.

## Sync, dedupe and precedence

Checkpoint is per `(app_owner,device_installation,type,policy_version)`; anchored-query tokens remain opaque native/device-local durable state (secure platform storage appropriate to size). Server records batch receipts/import progress, not authoritative Apple anchors; logout/account change isolates/reset consent. App advances anchor **only after backend transaction ACK and durable local checkpoint write**. Crash after ACK/before checkpoint causes same batch replay and must be harmless. Query reset/lost anchor triggers bounded rescan; dedupe remains independent of cursor. Unsupported type/permission change yields per-type status without breaking other types.

Planned backend `import_batches` receipt + source identities enforce unique owner/platform/type/source namespace/external sample UUID for low-frequency/workout/sleep rows; that sample identity namespace excludes device installation so the same sample replayed from two installations still dedupes; aggregate key `(owner,installation,metric,local_date,timezone,policy_version)` plus update revision/content hash. Resolve device-installation registration per authenticated owner, never caller owner field. Replayed same key/hash returns existing results; changed content updates revision/history rather than a duplicate. For aggregates produced by overlapping installations, analytics chooses one declared preferred source/installation; never sums duplicate device-day summaries. Source-priority configuration/history belongs to Health, not hardcoded per screen.

Retain distinct manual/imported rows; do not overwrite user-confirmed manual observations or silently merge same-day weights. For exact comparable metric+instant, manual confirmed wins representative selection; non-overlapping samples remain separate and latest time rules apply. For interval/day aggregates, selected source is declared per metric/window, default a stable platform/device priority, user override explicitly recorded. Source precedence changes trigger derived recompute/stale marking, not rewrite provenance. If a user edits imported value, preserve original imported revision and correction/user-confirmed provenance; later sync must not erase it. Store an explicit user override or linked correction with defined selection, and report conflict if changed source data needs review.

Native deletion records map to tombstones by source UUID: archive only corresponding imported object/revision, retain history and invalidate downstream signals. Do not cascade into manual edits/related goals/proposals; mark evidence stale. Aggregate-source changes/deletions require recomputation of affected day from current HealthKit data before updating summary. Tombstones prevent bounded requery resurrecting a removed sample; identity retention policy reconciles Phase 9 deletion. Revoked permission alone never deletes prior data; communicate that inability to read is not proof samples were removed.

Planned authenticated `POST /imports/healthkit/batches` accepts bounded batch≤200 normalized entries/1MB with batch UUID, device installation/type/policy, normalized entries/tombstones and content hash. One transaction validates owner/schema, applies dedupe/revisions and records receipt; malformed item rejects whole batch with index-only sanitized errors, no partial ACK/checkpoint advance. Split batches deterministically upstream; no indefinite retry of invalid entries. Limit retries/backoff and surface failed type; revoked/401 pauses until reauth/permission review. No anchor/health payload in logs. GET status returns counts/times/last error code only; optional batch receipt query resolves uncertain outcome.

## UI and execution packages

Health connections/settings surface: explanation/type toggles/lookback/retention/privacy, request permission, sync now, last successful type sync/counts, unknown/no-data/denied/unsupported/partial/error. Today/Insights imported origin/coverage visible; manual logging unaffected. No fake continuously syncing claim, no wholesale import progress bar based on unknown totals. Interrupted/network/offline retries respect receipt/checkpoint. Accessibility and account-switch clearing required.

`P8.1 compatibility/privacy/policy -> P8.2 normalization/native fake + P8.3 backend ingest -> P8.4 coordinator/UI -> P8.5 real-device verification`. Native/library proof gates live integration; mapping fixtures and backend tests can proceed without Apple credentials.

### P8.1 — Freeze supported types and real-device prerequisites

**Dependencies:** reconciliation. **Goal:** supported selective native contract.

**Areas:** mobile manifest/package/config, native adapter contract (provisional), deployment/security/data docs.

**Work:** official Apple/Expo/library verification, dev-build/entitlement procedure, retention/source-priority/permission states and consent/account policy.

**Requirements:** native isolation, no unverified permission assumptions, dated external gates. **Tests:** shared package native-import boundary check, unsupported/disabled capability fixtures. **Acceptance:** compatible build demonstrated or blockers explicitly prevent live enablement. **Out of scope:** other health platforms/types/write-back.

### P8.2 — Normalize bounded native reads

**Dependencies:** P8.1. **Goal:** minimal typed imports without raw mirror.

**Areas:** mobile-only adapter/mappers and separated fixtures; domain catalog/schema extension proposals.

**Work:** anchored reads for supported samples, platform/statistical aggregation proof, UTC/zone/unit/source metadata mapping and bounded initial windows; deletions/affected-day recompute.

**Requirements:** high-frequency samples never in transport; deterministic method versions/coverage. **Tests:** sleep overlap/DST/workout/weight/unit/delete fixtures, no-data/permission unknown, raw HR stripped, multiple-source aggregates. **Acceptance:** mappings match documented normalized schemas and retention policy. **Out of scope:** server AI analysis of raw samples.

### P8.3 — Transactional owner-safe ingestion

**Dependencies:** P8.1/P8.2 contract agreement and Phase 7 invalidation hooks. **Goal:** safe repeatable canonical import.

**Areas:** API/application/persistence/migrations/contracts/client; provisional import receipts/source identity/correction policy.

**Work:** additive metrics/import metadata, bounded batch validation, dedupe/content revisions/tombstones, receipt lookup and source selection/invalidation; preserve manual corrections.

**Requirements:** all-or-nothing batch, source namespace owner-scoped, no anchor as authorization. **Tests:** PostgreSQL replays/reordered overlapping batches/concurrent installs/malformed rollback, changed source vs user edit, cross-owner IDs, aggregate precedence and stale insight. **Acceptance:** same sample/day cannot double count across retries/devices; corrections survive. **Out of scope:** bulk mirror/queues/provider records.

### P8.4 — Checkpoint coordinator and connection UX

**Dependencies:** P8.2/P8.3. **Goal:** recoverable optional sync.

**Areas:** mobile adapter/coordinator/settings/Today/Insights/tests; public config/dev-build docs.

**Work:** account/type consent and local checkpoint storage, ACK-before-advance, bounded retry/status, type toggles/foreground sync and best-effort background only after correctness; source indicators/priority settings.

**Requirements:** no auto import after account change; disable stops reads/uploads; checkpoints never clear server history. **Tests:** crash before/after ACK, local checkpoint failure, lost anchor/rescan, offline/token expiry/revoke/account switch, UI partial status. **Acceptance:** fake coordinator scenarios recover without duplication and manual app unaffected. **Out of scope:** guaranteed background cadence.

### P8.5 — Verify first wave on actual iOS device

**Dependencies:** all packages and physical device/Apple capability gate. **Goal:** honest release evidence.

**Areas:** integration test runbook/fixtures; provisional phase-8 evidence.

**Work:** actual permission/no-data behavior, real workout/sleep/steps/weight/resting-HR/summary reads, sync twice/interrupt/revoke/change source, inspect normalized network/log output with consenting synthetic/test data. Verify background separately if enabled.

**Requirements:** mocks do not prove entitlements/data delivery/privacy/store approval. **Tests:** first-wave device matrix, disabled/unsupported regression, server/frontend checks and actual build. **Acceptance:** each enabled type has real evidence; unverified types remain disabled and phase completion states limits. **Out of scope:** releasing every Apple type or claiming store approval automatically.

## Migration, rollback and verification matrix

Additive schema/import identities, reusable Event/Observation history. Disabling adapter stops sync; receipts/tombstones stay to protect retries if reenabled. Policy-version change requires bounded rescan/recompute with explicit precedence across old/new aggregate versions, never sum both. Rollback stops client/server imports before incompatible schema changes; do not delete imported health data automatically. Phase 9 erasure must include local checkpoints and import identity cleanup and prevent automatic reimport without renewed consent.

| Risk                           | Offline/DB evidence                              | Required real gate                               |
| ------------------------------ | ------------------------------------------------ | ------------------------------------------------ |
| Native isolation/compatibility | Dependency graph/config/static boundary          | iOS dev build/entitlements/library compatibility |
| Permissions/account privacy    | Fakes/consent/account-switch tests               | Actual API read-authorization/no-data behavior   |
| Selective retention            | Fixture/network serialization raw-data exclusion | Inspect real normalized upload and logs          |
| Dedupe/cursors/deletes         | Replays/races/ACK crash/tombstone fixtures       | Real anchored-query reset/delete/revoke behavior |
| Aggregation/precedence         | Multiple sources/DST/correction goldens          | SDK aggregate source semantics on actual data    |
| Background                     | Coordinator tests/disabled paths                 | Actual delivery/OS constraints if enabled        |

## Acceptance, completion review and handoff

First-wave types import selectively with owner consent, correct source/time/coverage, stable dedupe/retry, manual correction protection and analytics invalidation. No raw high-frequency cloud mirror, native shared imports or mandatory device dependency. A mock-only implementation cannot call HealthKit phase fully verified.

Before Phase 9: Can every imported row/summary be traced to source/policy/receipt? Does account change require renewed consent? Are deletes and manual corrections safe? Is no-data interpretation honest? Are real-device gates complete for every enabled type?

Luna Max must create planned `docs/implementation/evidence/phase-8-release.md`: native/library/build versions, entitlements/permission behavior, selected type/schema/retention mappings, source precedence and policy version, migration/head/import API/receipts, checkpoint/retry/tombstone contract, generated commands, offline vs actual device results, background/store/privacy external gates and disabled capabilities. Include exact cleanup requirements for Phase 9 erasure.
