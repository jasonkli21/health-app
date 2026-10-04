# Phase 2 — Daily health data

## Implementation-time reconciliation gate

**Status: planned. Dependencies: Phase 1 accepted and its release evidence available.** Read [Phase 2 roadmap](../implementation-plan.md#phase-2--daily-health-data), Phase 1 evidence (planned `docs/implementation/evidence/phase-1-release.md`), current schemas/migrations/owner repositories, generated contracts, mobile test runner and local setup. Confirm actual temporal, revision, create-retry and permission semantics before extending them. Record drift and update this plan/ADR first for material changes.

Phase 0 directories are real: `services/api/src/health_api` layered service, `services/api/tests`, `migrations`, `contracts/openapi`, `packages/api-client`, `apps/mobile/app`, `src`, `tests`. Phase 1 Profile/client/history are assumed completed, **not present in the planning baseline**. All new modules/routes/tables below are planned/provisional and must use actual Phase 1 conventions.

## Outcome / scope

**Deliver:** manual structured logging in nutrition, exercise, sleep, symptoms and measurements; Events and Observations; owner/date-scoped Today timeline; deterministic daily summaries; universal structured Add and Profile↔Today navigation.

**Defer:** natural-language capture until read-only Assistant in Phase 5 and typed proposals in Phase 6; medication regimens/planning to Phase 4; automatic/device data to Phase 8; document/lab import to Phase 9; AI summaries/cloud/web. No fake completion scores or universal nutrient database.

## Event versus Observation contract

An **Event** represents something that occurred (meal, workout, sleep episode, symptom episode). An **Observation** represents a measured/reported value (weight, symptom severity, exercise duration if measured). An event may reference observations through an owner-scoped typed relationship, but the same quantity must not be counted from both the event payload and its linked Observation. Declare one authoritative metric carrier per schema. Profile remains effective background, not daily event storage.

Both use the Phase 1 envelope/source/revision/history. Planned `events` subtype adds type, occurred_at and optional ended_at; `observations` adds metric key, observed_at, optional interval_end, value_kind and queryable quantity/unit or boolean/text value columns. Validated JSONB stores type-specific details; common time/type/unit keys remain relational. An Observation value is present and typed; missing observations are absent rows, not null placeholders/zero. Partial events may have omitted optional quantities; summaries report coverage. Capture timezone and time precision alongside UTC instants. Date-only input is represented explicitly as local date/time precision and cannot be fabricated as an exact midnight sample; derive interval bounds with the recorded IANA zone for day queries.

| v1 input                 | Planned minimum payload / normalization                                                                                                | Today summary                                                                     |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| Nutrition meal Event     | Label/time required; optional foods/notes and finite nonnegative energy quantity; no assumed nutrients                                 | Logged meals/count; known energy subtotal with completeness annotation            |
| Exercise workout Event   | Activity label/type, start, optional end; optional duration/distance with explicit units                                               | Logged activity; known duration subtotal; no calorie inference                    |
| Sleep episode Event      | Start/end if known, optional quality rating with defined ordinal scale                                                                 | Episode segments overlapping day; known total duration, explicit missing coverage |
| Symptom episode Event    | Symptom label/time, optional severity on documented 0–10 scale and duration                                                            | Reported symptoms, no absence inference on unlogged days                          |
| Measurements Observation | Metric from initial catalog: weight (kg/lb), temperature (C/F), systolic/diastolic pressure (mmHg), pulse (beats/min); value/unit/time | Latest explicitly recorded measurement, no averaging unlike quantities            |

Support symptom severity as a linked Observation when recorded, with Event payload referencing its ID rather than a duplicate numerical field. Blood pressure may be a pair of linked metric observations created atomically in one Add transaction. No diagnosis from values, no user-unrequested prescriptions. Bounds prevent malformed/unit-incompatible/non-finite values without excluding legitimate unusual measurements through undocumented clinical assumptions. Keep original quantity/unit; known conversions are versioned deterministic server utilities. Persist computed rollups only if necessary after profiling; initially query/compute on demand over indexed rows.

## API, day boundaries and UI

Planned `GET/POST /events`, `GET/PATCH/DELETE /events/{id}` and equivalent `/observations` follow Phase 1 owner/ID/revision/archival contracts. Lists require bounded time filters where useful, default page 50/max100 with stable `(occurred_at,id)` or `(observed_at,id)` cursors. Limit spans to 366 days; reject invalid/reversed ranges. Creation accepts caller UUID; identical retries return existing resource, conflicting reuse 409. Updating/archiving appends history. Server-derived provenance for manual explicit saves is manual + user_confirmed. Reject caller spoofing of device/AI/import source. A compound Add endpoint, provisionally `POST /daily-entries`, accepts a bounded Event plus its linked Observations (max20), with unique IDs and atomic transaction; omit it if the chosen forms never require compound writes, documenting equivalent atomic service behavior.

`GET /today?date=YYYY-MM-DD&timezone=<IANA>` defaults to principal zone, returns date/zone/as_of, bounded timeline page, profile-context references valid that day, and summaries with `known_value`, `unit`, `logged_count`, `coverage`, `method_version` and `partial`. It does not include future plan/insight resources yet. Date selects a local calendar day mapped to `[start,end)` UTC, including 23/25-hour DST days. Timeline includes instants within day and intervals overlapping it; allocate additive duration by overlap to avoid counting a full overnight episode twice. Latest measurements choose observed time/ID deterministically, not request arrival time. Empty summary has null known_value and “not logged”; explicit zero recorded yields zero and logged_count>0. Nutrition/exercise known subtotal never means complete intake/activity. Same metric from multiple manual rows uses declared sum/latest/episode rule, not an arbitrary generic aggregate.

Define summary/timeline snapshot consistency: queries use a shared DB transaction/as_of, return revision references, and paginate stably; concurrent new logs may appear on explicit refresh, not shift previously returned rows. Coverage describes available logging, not sensor completeness or proof the person did nothing. No hidden persistent materialization.

Mobile planned features `src/features/today`, `src/features/add` and tests in `tests/today`, `tests/add`; app routes connect Profile and Today with accessible universal + Add. Type chooser→small optional form→preview where compound data warrants it→explicit save. Default current time is editable/visible; do not default quantities to zero. Recover draft in memory on error; reusing submission UUID prevents duplicate saves. Server rejects bad units/fields visibly. Offline: readable in-memory last result with stale label, save unavailable/retry when connection returns; no automatic write queue. Loading/empty/error/refetch, long timeline paging and day/zone selection handled. Existing Profile paths retain their behavior. No empty Assistant/Plan/Insights tabs just for symmetry.

## Order and vertical work packages

`P2.1 domain semantics -> P2.2 persistence/commands -> P2.3 Today/API/client -> P2.4 mobile Add/Today -> P2.5 regression/evidence`. Rollup fixtures can proceed with P2.1; Today rendering starts only after its DTO is agreed/generated.

### P2.1 — Daily schema catalog and rollup rules

**Dependencies:** Phase 1 reconciliation. **Goal:** deterministic meaning for every log.

**Repository areas / planned artifacts:** domain schema registry/quantity/time utilities, model/API docs, synthetic daily fixtures in `services/api/tests`.

**Work:** register only the five initial domains, define Event/Observation distinction and authoritative metric carriers, unit conversions/rating scales/precision rules; specify sum/latest/interval aggregation and sparse coverage. Define max string/body/compound bounds in schemas.

**Requirements:** typed/versioned payloads; no invented observations; manual origin independent from confirmation. **Tests:** zero/false/absence, invalid metrics/units, overnight/DST/date-only/late logs, conversion round trips, double-count prevention. **Acceptance:** fixture expectations agree with documented Today outputs. **Out of scope:** trackers, AI parsing, device precedence.

### P2.2 — Persist and revise daily entries atomically

**Dependencies:** P2.1. **Goal:** durable owner-safe daily state.

**Areas:** existing migrations, persistence/application layers; provisional Event/Observation repositories/commands and compound Add service.

**Work:** additive tables/indexes by owner/type/time and FK consistency; create fingerprints/retry safety, link observations, revisioned correction/archive; use existing source/history infrastructure, no second envelope/history store.

**Requirements:** all linked IDs owner-resolved; blood pressure/compound save commits together; history retains original unit/time. **Tests:** PostgreSQL migration cycle, cross-owner linked write, interrupted compound transaction, duplicate IDs/retries, late correction/archive/refetch and concurrency. **Acceptance:** DB survives restart and failure never produces half an entry. **Out of scope:** scheduled logging, automatic imports, background job infrastructure.

### P2.3 — Expose daily routes and Today read model

**Dependencies:** P2.2. **Goal:** one consistent query contract.

**Areas:** API/application layers, OpenAPI export and `packages/api-client`; provisional Today query/read DTO.

**Work:** thin resource routes and Today query, bounded filters/cursors, sanitized errors, day-zone boundaries and per-domain summaries; regenerate client, check previous Profile contracts remain compatible.

**Requirements:** 404 foreign IDs, 409 stale/reused IDs, 422 unsupported schemas/time filters; no health values in error logs. **Tests:** two-owner route matrix, time-window paging, consistent timeline/summary snapshots, unknown-vs-zero DTOs and clean generation. **Acceptance:** API returns correct sparse Today fixtures and handles DB failure with recoverable 503. **Out of scope:** plans/insight cards and full-text health search.

### P2.4 — Manual Add and Today on mobile

**Dependencies:** P2.3. **Goal:** useful daily logging.

**Areas:** existing mobile app/src/tests; provisional Add/Today features and client query bindings.

**Work:** implement small schema-specific forms, explicit unit/time selection and save, day timeline/summaries/profile link; avoid shared UI extraction beyond demonstrated reuse.

**Requirements:** keyboard/font/accessibility support, no zero placeholder disguised as a result, one submission UUID per draft, conflict requires refetch. **Tests:** all five forms success/invalid/unit/unknown/time cases, retry without duplicate, network failure/draft preservation, empty/partial Today and paging. **Acceptance:** actual device user logs each domain and sees accurate Today; Profile edits still work. **Out of scope:** natural-language entry, offline queue, native permissions.

### P2.5 — Validate daily semantics end to end

**Dependencies:** all previous packages. **Goal:** reliable input base for cloud/planning/analytics.

**Areas:** CI/tests, local/data/API docs; provisional phase-2 release evidence.

**Work:** multi-day sparse fixtures and replay correction/archive scenarios through actual generated client; performance check bounded Today queries; document actual metric catalog and missing optional quantities.

**Requirements:** reproducible synthetic data only. **Tests:** API/mobile regressions, migration/head, logs privacy, query count/index review. **Acceptance:** evidence includes fixed expected rollups and no future functionality. **Out of scope:** statistically inferred health conclusions.

## Compatibility, failure and verification

Additive migrations preserve Profile IDs/revisions/permissions. Downgrade only synthetic data; stop serving routes before reverting subtype schema. No materialized summaries to go stale; if introduced for measured need, document invalidation for revision/archive before completion. APIs maintain stable operation IDs; regenerate client in same change. Rollup computation must have deterministic tests before UI asserts it. Retrying uncertain POST uses same UUID, never generates a fresh one automatically.

| Risk                       | Offline CI / local DB evidence                        | Manual/external                   |
| -------------------------- | ----------------------------------------------------- | --------------------------------- |
| Sparse quantities and time | Golden fixtures, DST/overlap/conversion tests         | User zone walkthrough             |
| Authorization/atomicity    | Two-owner PostgreSQL, linked-write rollback and races | Docker setup                      |
| Today/read consistency     | Cursor/snapshot tests, bounded query profiling        | Representative device latency     |
| Add UX                     | Component/generated-client integration                | Actual iOS keyboard/accessibility |
| Compatibility              | Profile regressions, migrations, schema/client diff   | No cloud claim                    |

## Acceptance, completion review and handoff

A local user can log/edit/archive each supported daily type, navigate Profile/Today, and see accurate sparse summaries across calendar boundaries without doubled linked quantities. No later-phase code. Ownership/revisions/provenance are preserved and foundation/product checks pass.

Before Phase 3: Are Event/Observation responsibilities and rollup methods unambiguous? Do late edits and unknowns render correctly? Are compound writes/retries safe? Are query bounds/indexes explicit? Is device behavior verified or gated?

Luna Max must create planned `docs/implementation/evidence/phase-2-release.md`: actual migration head, metric/schema catalog and examples, routes/error/ID/revision contracts, Today DTO/method versions/day semantics, generated procedure, mobile/API test commands/results, representative query costs, unresolved external checks and Phase 3 deployment prerequisites. Include synthetic DST/sparse fixtures for later analytics evaluation.
