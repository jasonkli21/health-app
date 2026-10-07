# Phase 2 independent review

Main-session review of Phase 2 through `61d09ac`, 2026-10-04 PDT.
Reviewed the phase plan/reconciliation, prior foundation, migrations/models,
daily schemas/unit/time/rollup rules, transactional services, snapshot queries,
daily routes/serializers/cursors, generated client, mobile form/builders/screens,
and tests/evidence. Code re-review is complete; Phase 3 must wait for the
PostgreSQL verification gate described below.

## Required fixes

1. **P1: wrong resource DELETE mutates before 404.** `delete_event` and
   `delete_observation` call `archive_daily_item` before testing subtype. Thus
   `/events/{observation_id}` can archive an Observation and append history,
   then report not found; the reverse also happens. Enforce expected object type
   inside the write transaction before mutation. Test both wrong-type routes,
   no state/revision/history/sequence change, and normal archive behavior.
2. **P2: daily edit draft loss.** DailyEditScreen hides/unmounts its internal
   form on every focus fetch and keys it by refresh/revision. Failed-save/dirty
   drafts disappear on blur/refocus or failed reload. Apply the actual
   draft-retention behavior established for Profile, retaining original revision
   until an explicit successful conflict reload/save/cancel. No editing of a
   stale item from another route ID. Add actual state/flow regression tests.
3. **P2: Today stale snapshot pagination during refresh.** A same-day refresh
   starts a new request scope but retains `data.next_cursor` from the old result;
   loadMore stays enabled while the first page is pending. Its old-snapshot page
   can be accepted under the new scope and append to the refreshed items. Block
   pagination until the current first page succeeds (including failed refresh
   with stale data), bind accepted page sequence/date/zone to the visible result,
   and test out-of-order refresh/page responses. Reset DailyHistory loadingMore
   on scope reset too; its stale request's finalizer is suppressed by the guard.
4. **P2: destructive interval edits.** Daily `buildEvent` always sends
   `ended_at=null` for a symptom; `buildObservation` always sends
   `interval_end=null`. Notes/value edits of valid API-created interval entries
   silently erase bounds. Preserve all supported time fields in draft roundtrip
   and expose/edit optional symptom and Observation ends, or explicitly preserve
   unsupported editable fields; do not silently drop them. Test original-unit,
   microsecond time and interval roundtrips through generated DTO builders.
5. **P2: missing partial sleep support.** The plan requires start/end if known
   and explicit missing coverage. Backend forces sleep end; form forbids
   date-only sleep, so a person cannot log sleep without inventing a duration.
   Support sleep with a known date or start and unknown end while returning null
   duration with partial coverage, retaining exact intervals when supplied.
   Update schema/model DB checks additively, mobile, fixtures and docs together.
6. **P2: summary overflow and sparse severity coverage.** Individually finite
   quantities can overflow unit conversion or sums (`1e308` duration hours or
   two large kcal rows), causing Today to fail rather than return valid JSON.
   Specify safe deterministic numeric bounds/overflow behavior with clear input
   errors and no undocumented clinical limits; test conversion and aggregate
   overflow. Severity latest coverage currently counts only present observations
   and can show complete logging for one rated episode among many unrated
   symptoms. Define severity coverage relative to eligible logged episodes and
   test missing and archived linked observations without counting twice.
7. **P2: snapshot query work is not bounded by candidate cap.** Candidate
   DISTINCT may scan arbitrarily many revisions and latest GROUP BY aggregates
   all prior revisions per candidate. Use index-supported latest lookups and
   an explicit operational bound for pathological history scans (e.g. enforced
   statement timeout with sanitized recoverable failure); measure EXPLAIN/query
   counts/latency on sparse and high-revision owners. Keep canonical immutable
   revisions and correct past cursor results, avoid new materialized stores.
8. **P2: compound sequence exposes partial committed state.** A compound save
   allocates a different daily sequence to each object. Unsigned cursor JSON can
   name a sequence in the middle of that save (decoder accepts any integer <=
   current), returning an Event without its atomically saved Observation.
   Make snapshot markers represent only committed transaction boundaries, e.g.
   one sequence shared by all objects in a compound transaction, and reject
   intermediate legacy markers if necessary. Test atomic snapshot consistency
   and retries/rollback/concurrency. Do not solve by weakening the guarantee.

## Implementer disposition (2026-10-04; root re-review pending)

All eight premises were confirmed against the implementation. The corresponding
fixes and regressions are committed in `a24c48a` (backend) and `435f396`
(mobile); this document records their evidence and root re-review status:

1. DELETE now passes the expected subtype into the transactional archive
   command; wrong-type paths are covered for both resource routes.
2. Daily edit state retains dirty drafts and their original revision across
   focus refreshes and failed loads; only a successful explicit conflict reload
   replaces the baseline.
3. Today paging binds the first page and each continuation to scope, date, zone,
   and sequence; old cursors are disabled during pending or failed refreshes.
4. Event and Observation builders/forms roundtrip editable interval ends, units,
   date precision, timezone, and microsecond timestamps.
5. Sleep accepts a date or start without an end; missing duration stays unknown
   and partial.
6. Daily inputs and converted quantities have explicit software bounds;
   checked sums reject overflow. Severity coverage uses eligible linked
   Observations against active episodes and excludes archived links. Domain,
   API, and sparse-coverage regressions were added.
7. Today uses an indexed correlated latest-revision lookup, retains the candidate
   cap, and sets a two-second PostgreSQL-local timeout. Fresh PostgreSQL startup
   retries still fail with shared-memory `ENOSPC`, so database timing, query
   plans, and route execution remain unverified.
8. Compound writes share one sequence and write a marker in the same
   transaction; the additive migration retains revision history and recognizes
   only sequence zero and each owner's legacy current state as old cursor
   boundaries. Rollback and boundary assertions were added.

## Main-session re-review disposition

Root independently re-reviewed the backend transaction/type guards, compound
sequences and marker migration, snapshot query/timeout, rollup semantics,
mobile edit-state wiring, interval roundtrips and paging guards. The eight code
findings are addressed. Database-dependent acceptance remains open, particularly
the actual latest-revision query plan and performance under long histories.

One residual numeric-validation bypass was reproduced: Pydantic accepted the
string `"1e308"` because the software bound ran before float coercion. The bound
now runs after coercion, while the separate boolean rejection remains before
coercion. Three numeric/string regression cases pass. Contract regeneration has
no tracked diff. Root reran the full available suite: **42 Python tests passed,
40 PostgreSQL tests skipped; 54 mobile tests passed across 11 files**. Configured
CI Ruff check/format (36 files), mypy (21 sources), scaffold verification,
mobile TypeScript/ESLint and generated-client TypeScript passed.

Phase 2 is implemented and code-reviewed, but is not verified complete. Resume
with an authorized disposable PostgreSQL database: run all 82 Python tests,
fresh and existing-data migrations and drift checks, and record representative
EXPLAIN/ANALYZE and latency for sparse and high-revision owners. Investigate and
delegate any substantive failures before closing the phase. Do not start Phase
3 while these checks remain blocked. No unrelated cluster or IPC cleanup is
authorized by this checkpoint. This was the Phase 2 review stop condition;
Phase 3 was authorized later and is recorded in its own release evidence and
the current-state page.

## Verification and handoff

Use a few logical commits, actual behavior tests for asynchronous screen logic,
full Profile regressions, deterministic contract regeneration, static checks and
iOS bundling. Keep API handlers thin: snapshot orchestration/rollup/domain rules
belong in application/domain rather than growing the 900-line route module.
Split only along actual responsibilities while addressing the fixes.

P2.3 database tests and measured query costs are still required. The host shared
memory gate is genuine; only an isolated authorized PostgreSQL cluster/database
may be used. Other task-owned clusters/IPC must stay untouched. Retry safely if
resources have cleared, otherwise complete code/tests/evidence and report the
remaining verification blocker. Never claim skipped tests passed. Preserve
PG17/Docker/pinned-pnpm/full-CI/native-device/advisory gates accurately. Do not
start Phase 3. Root will independently re-review and close accepted results.
