# Phase 4 — Personal planning, contexts and custom trackers

## Implementation-time reconciliation — October 5, 2026

Phase 4 was implemented against the repository after Phase 3 local review. The
user explicitly authorized this phase. Phase 2 PostgreSQL acceptance and Phase
3 live-cloud acceptance remain inherited, unverified release gates; this work
does not claim either gate passed.

The planned paths were provisional. The actual API is under
`services/api/src/health_api`, migrations use the current Alembic head
`c3721f5a9a01`, generated DTOs come from FastAPI OpenAPI, and mobile features
live under `apps/mobile/src/features` behind Expo Router. Phase 1–3 already
provide the owner-scoped envelope, manual source, revision snapshots, verified
cloud owner dependency, Event/Observation storage, and Today snapshot paging.

The implementation follows these reconciled decisions (see
[ADR 0008](../../architecture/adr/0008-planning-tracker-storage.md)):

- Extend the existing envelope type/domain checks and add owner-consistent
  subtype, plan-item, schedule-version, occurrence-override, and tracker-schema
  tables. Do not create a second planner store or generic object-write route.
- Keep envelope status `active`/`archived`; goals, regimens, plans, contexts,
  and tracker definitions keep their richer lifecycle in typed subtype rows.
  Revision snapshots include the subtype state. Manual writes remain
  `user_confirmed` and permissions default to false.
- Preserve existing Event/Observation rollup meanings. Custom tracker entries
  use the existing Observation envelope/subtype and immutable tracker schema
  version; they do not participate in Phase 2 numeric summaries unless they
  declare a supported metric/unit mapping.
- Today adds planning items and active contexts additively. Schedules expand
  only for bounded reads; occurrence keys use the original local slot and
  survive schedule revisions. Overrides are owner-resolved and revision
  checked.
- Phase 2 database test skips and Phase 3 real cloud/manual checks remain
  explicit release evidence, not blockers to local implementation.

## Implementation-time reconciliation gate

**Status: planned. Dependencies: accepted Phases 1–3.** Read [Phase 4 roadmap](../implementation-plan.md#phase-4--personal-planning), actual preceding evidence, object/schema/history/ownership conventions, Event/Observation and Today contracts, cloud auth and mobile features. Inspect generated DTOs and migration head. Record drift; update material design/ADR before code. Do not reuse a provisional path blindly.

Existing Phase 0 homes are `services/api/src/health_api/{domain,application,api,persistence}`, `services/api/tests`, `migrations`, `contracts/openapi`, `packages/api-client`, `apps/mobile/{app,src,tests}`. All features/contracts below are **planned/provisional**, including preceding product modules absent from today's scaffold.

## Goal / boundary

**Deliver:** a useful non-AI planning product: goals, regimens, plans, temporary active contexts, structured custom trackers, explicit schedules and Today plan items. Users organize intended behavior and log what actually happened without conflating intent with events.

**Defer:** AI-authored plans/schemas until Phase 6, automated insights/experiments until Phase 7, reminders/push notifications unless separately authorized, HealthKit/document import/web, a full clinical medication-management engine or arbitrary RRULE editor. Manual medication/supplement regimen and habit intent fit this phase; never suggest dosages or infer adherence.

## Model and schedule contracts

All resources extend Phase 1 health_objects/source/revision/history and permission semantics. Add only needed subtype tables and indexes, with owner-consistent relationships. Use existing quantities/schema registry and explicit manual saves. No parallel planner datastore.

| Planned resource    | v1 contract / lifecycle                                                                                                                                                               |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Goal                | Label, domain, optional metric target `{metric, comparator, quantity}`, target period/dates; active/paused/completed/archived; manual completion, no invented progress                |
| Regimen             | Label, kind habit/medication/supplement/activity, optional user-entered quantity/unit/instructions, schedule reference; no drug interaction/dose advice                               |
| Plan                | Label/validity, ordered items referencing owner goals/regimens or explicit manual tasks; item stable UUID, optional schedule; active/paused/completed/archived                        |
| Context             | Label/type, validity window, bounded notes and typed relevance/priority; active/ended/archived; optional explicit links to affected goals/regimens/profile                            |
| Tracker definition  | Name/domain, immutable versioned field schema, active/archived; primitive text/number/boolean/enum/date plus quantity with supported unit, field IDs and optional required constraint |
| Schedule            | Owner resource/item ID, IANA zone, local start date/time, daily or weekly recurrence, selected weekdays/interval, optional end date; revision/history                                 |
| Occurrence override | Owner, stable occurrence key, expected schedule revision, state completed/skipped/rescheduled, optional linked actual Event/Observation; historical action timestamps                 |

Allowed status transitions must be enumerated per resource; map queryable envelope status active/archived to subtype lifecycle consistently. Paused/completed are not deleted. Goal progress derives from known manual observations with declared metric/time window only if feasible; display unknown when coverage insufficient, no analytics claims. Initial goal metrics reuse Phase 2 catalog or custom tracker numerical field; don't invent new measurement kinds without registry tests.

Active contexts never overwrite baseline Profile. At an as_of instant, include only applicable contexts, sort explicit priority then validity/ID deterministically, and show overlapping conflicting contexts without claiming a resolved clinical truth. Context is temporary relevance, not authority to suspend medication/regimen. User must explicitly edit/pause those. Expired contexts disappear from active Today but remain in history.

Schedules represent intent. Expand occurrences in the API for a bounded date range (default Today, max31 days/response max500), not indefinitely in the database or a background bus. Stable occurrence key derives from resource/item ID, schedule identity and original local date/time; schedule revision participates in command validation but not in identity for unchanged slots. Editing a schedule creates a new effective version; preserve prior occurrence status and never retroactively rewrite completed/skipped items. Define explicit effective boundary for edits; ambiguous changes require user choice, default future-only. On spring DST gap use next valid local time; on fall overlap use earlier offset once, record resolution in occurrence DTO. Zone change is explicit with future effective date, historical keys unaffected. Overnight duration semantics remain Phase 2's, not planner rules.

`completed` occurrence is a user assertion; it creates no measurement/event automatically. Optionally link an existing owner Event/Observation, or explicitly choose a logging form in Add and commit log+completion atomically. Unmarked occurrence means unknown/not recorded, not missed/nonadherent. `skipped` is explicit. Rescheduling records original key and new due instant, prevents a duplicate original presentation, and validates bounds/current revision. No auto-medical interpretation of adherence.

Custom tracker v1 fields max20, enum choices max50, text max2000, definition metadata max16KB; required only when user elects required. No code, expressions, regex execution, arbitrary recursive JSON schema, HTML, external references or computed clinical rules. Field IDs stable; schema version immutable once entries exist. Definition edit creates new version; removing/changing field type does not revalidate historical data against the new version. Log custom entries as Phase 2 Observations with `tracker_id`, `tracker_schema_version` and values keyed by field ID; no new competing generic tracker-entry store. Numeric fields can participate in future analytics only with explicit unit/metric semantics. Empty optional field is absent/unknown, explicit false/zero kept; no entry means no observation.

## API and mobile behavior

Planned typed CRUD resource groups `/goals`, `/regimens`, `/plans`, `/contexts`, `/trackers` follow established create UUID/revision/archive/error/pagination contracts. Use bounded stable filters; owner list page50/max100. Planner operations include typed lifecycle transition, schedule edit effective date, and planned `PATCH /plan-occurrences/{key}` with expected schedule/override revision. Keys never grant access: resolve owner/resource. 409 stale schedule/action; 422 invalid recurrence/field/reference; 404 foreign ID. Repeat same occurrence action is idempotent; conflicting state change requires current revision. Plan item reorder replaces bounded order with exact stable item IDs; duplicates/foreign/missing IDs reject.

Tracker create/edit/read returns definition versions; `POST /observations` gains a typed tracker-entry variant validated against the specified immutable owner definition. Historical reads use that version. An archived tracker stops new logs but history remains readable. Regenerate OpenAPI/client together; extend Today with `plan_items`, `active_contexts` and optional goal summaries, keeping Phase 2 timeline/rollup meaning unchanged. `GET /plans/{id}/occurrences` (or equivalent agreed route) uses explicit date/zone boundaries; malformed cursor/range rejects.

Mobile Plan surface groups goals/regimens/plans, context editor and tracker builder/entry; use feature modules inside `src/features` and separated tests. Today renders due/recorded/skipped/rescheduled/unknown states, with accessible actions and conflict/refetch. Universal Add offers active custom trackers without AI. Profile links to planning/context where meaningful; no all-in-one giant form. Loading/empty/error, archived detail, expired context, immutable old tracker schema and unavailable/offline service states explicit. In-memory drafts only; no offline queue. Server recalculation after edit, no frontend business rules duplicating recurrence.

## Dependency map / work packages

`P4.1 contracts -> P4.2 planning/context CRUD -> P4.3 schedules/Today`; `P4.1 -> P4.4 trackers/Add`. Both branches feed `P4.5 Plan/mobile/regression`. Work may proceed alongside fixtures after shared contracts agree, without parallel handwritten clients.

### P4.1 — Establish intent/context/tracker schemas

**Dependencies:** reconciliation. **Goal:** precise planning semantics.

**Areas:** domain registry/time/quantity rules, model/API docs; provisional payload schemas/fixtures.

**Work:** define table/payload fields, lifecycle transitions, reference bounds, context precedence visibility, recurrence/DST rules and immutable tracker versions.

**Requirements:** intent ≠ actual observation; no hidden overrides or inferred adherence. **Tests:** sparse goal target, invalid recurrence/timezone/transition, overlap context and primitive schema limits. **Acceptance:** agreed synthetic fixtures cover each resource and status. **Out of scope:** AI, clinical rules, arbitrary RRULE.

### P4.2 — Persist and expose planning/context resources

**Dependencies:** P4.1. **Goal:** editable canonical manual plans.

**Areas:** migrations/persistence/application/API/client; provisional planning repositories/services.

**Work:** additive subtypes and owner indexes, transactional plan-item references/reorder, lifecycle/history, context expiry query; CRUD routes/client generation.

**Requirements:** one envelope/revision store; all linked references owner scoped; expired context retained. **Tests:** migration cycle, two-owner resource/edge tests, stale writes/archive/reference cascade policy, failed reorder rollback. **Acceptance:** CRUD/queries/history survive restart locally/cloud. **Out of scope:** schedule materialization, insights.

### P4.3 — Schedule occurrences and Today integration

**Dependencies:** P4.2. **Goal:** visible intent with explicit recording.

**Areas:** application queries/time modules, provisional schedules/overrides migrations/routes, Today DTO.

**Work:** bounded expansion, stable keys/revisions, future-effective edits and DST resolution; occurrence action idempotency; optional atomic log-and-mark; Today due/unknown/skipped summaries.

**Requirements:** no duplicate slot from DST/retry; no auto-created observation; completed history immutable across schedule edit. **Tests:** daily/weekly intervals, leap day/DST/zone change, range bound, overlapping Today dates, edit/mark race, reschedule/retry and failed linked save. **Acceptance:** date fixtures deterministically produce intended occurrences without altering Phase 2 rollups. **Out of scope:** push scheduling/background calendar sync.

### P4.4 — Custom definitions and versioned logging

**Dependencies:** P4.1, actual Phase 2 Observation contract. **Goal:** extensibility with validation.

**Areas:** tracker subtype/repository/schema version validator, observation routes/client, Add feature.

**Work:** immutable definitions, definition-version APIs, typed custom Observation variant and historical decoder; manual builder/entry UI slice.

**Requirements:** archived definitions reject new entries; optional missing vs false/zero preserved; source/permissions inherited safely. **Tests:** old entries after field deletion/type change, malformed/foreign version, enum bounds, archive/new log and numeric unit compatibility. **Acceptance:** users define/log/edit a tracker without corrupting past entries. **Out of scope:** executable/computed fields and AI schemas.

### P4.5 — Complete Plan UX and system review

**Dependencies:** P4.2–P4.4. **Goal:** non-AI planning usable end to end.

**Areas:** mobile app/features/tests, API integration tests/docs; provisional phase-4 evidence.

**Work:** Plan overview/detail/edit flows, Today occurrence actions/context visibility, tracker Add and Profile links; review accessibility/retry/session-switch behavior and cloud parity.

**Requirements:** server-derived recurrence, clear unknown progress, no health logs. **Tests:** manual goal/regimen/plan/context/tracker scenario, conflict/offline/error/loading, golden Today regression, real mobile timezone/DST display. **Acceptance:** useful non-AI planning product, all evidence recorded. **Out of scope:** adding empty future navigation screens or importing device data.

## Migration/failure/rollback and verification

Migrate additively without changing daily/Profile object IDs. Retain immutable schedule and tracker versions referenced by history/entries; never cascade definition archive into observation deletion. Downgrades only on disposable DB after rejecting new-type writes; live rollback requires compatible old image or backup restore, not dropping recorded plans. Retry create follows existing fingerprints, mark follows occurrence unique key+revision. No scheduler daemon required; query failure displays retry instead of fabricating missed activity.

| Risk                   | Deterministic CI/local DB                               | Manual/external                     |
| ---------------------- | ------------------------------------------------------- | ----------------------------------- |
| Intent and context     | Lifecycle/overlap/expiry/reference tests                | UX review for unknown vs missed     |
| Recurrence             | Golden DST/leap/zone/edit/race fixtures                 | Real device display in chosen zones |
| Tracker history        | Versioned decoder and malformed-field tests             | Builder accessibility/keyboard      |
| Security/compatibility | Two-owner joins, atomic commands, migration/client diff | Existing staging parity scenario    |
| Today integration      | Before/after unchanged daily rollups, occurrence limits | Day navigation latency              |

## Acceptance / completion review / evidence

Accept when manual planning/tracking work with real Today, schedules remain correct around edits/DST, actual logs remain separate from intent, contexts never silently overwrite Profile, and historical tracker values remain readable. No AI/native/records/web or speculative infrastructure.

Before Phase 5: Are every lifecycle/metric/schema version and occurrence action precise? Are unknowns visible? Does context selection have deterministic relevance without clinical override? Can all active planning data be read through owner-safe services? Are mobile/cloud regressions green?

Implementing Luna Max must create planned `docs/implementation/evidence/phase-4-release.md` with migration head, actual routes/types/statuses/limits, schedule-key/edit/DST rules and fixtures, tracker version/entry decoder contract, Today additions, generated commands, mobile/local/cloud results, unresolved checks and context-builder consumption points.
