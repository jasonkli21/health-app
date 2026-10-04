# Phase 2 — Daily health data release evidence

Updated 2026-10-04 (PDT). Phase 2 implementation and P2.5 evidence are
committed through `61d09ac`. Independent-review fixes are committed as
`a24c48a` (backend integrity, semantics and queries) and `435f396` (mobile
draft and pagination behavior); this evidence/review checkpoint is the third
logical fix commit. Root's independent code re-review is complete; database
acceptance remains open. The backend fix
adds an additive cursor-boundary migration. PostgreSQL-backed API verification,
migration lifecycle/drift, and query-cost checks remain open because fresh
PostgreSQL 16 initialization still fails at shared-memory allocation.

## Delivery and persistence

Phase 2 is implemented in five vertical packages:

- `d46a139` — P2.1 schema catalog, time/unit rules, versioned summaries and a
  synthetic sparse fall-DST fixture.
- `9a3f911` — P2.2 additive Event/Observation persistence, links, owner write
  sequence, idempotent atomic create, revisions, archive and history.
- `d3aa0de` — P2.3 typed daily resource/history/compound/Today APIs, OpenAPI
  and generated contracts.
- `fcf1010` — P2.4 five-domain Add, Today, item detail/edit/archive/history,
  Profile navigation and mobile tests.
- P2.5 evidence and configured-lint import fixes are committed alongside this
  record. Review follow-up is grouped into backend (`a24c48a`), mobile
  (`435f396`), and evidence/checkpoint commits.

Alembic reports one head: `b9f5e1a72c4d` (offline graph and SQL generation).
Migration `b9f5e1a72c4d` drops per-object revision-sequence uniqueness, adds
transactionally written `daily_snapshot_markers`, and backfills sequence zero
plus each owner's current legacy sequence. The owner/object/sequence index
remains available for latest-revision lookups. The earlier migration adds
`events`, `observations`,
`event_observation_links`, the owner daily sequence and as-of query fields on
`health_object_revisions`. Existing `health_objects`, `sources`, and revision
history remain canonical; Profile routes and persisted data remain in place.
Owner-scoped foreign keys constrain links and subtypes. Event and Observation
indexes cover owner/time and owner/local-date lookups; revision indexes cover
owner/domain/instant, owner/domain/local-date, and owner/object/sequence reads.
The migration widens only the shared envelope checks needed for the two new
object types.

## Catalog and Today semantics

The v1 catalog supports five manual domains. Meals store optional energy
(kcal/kJ), foods and notes. Workouts store optional elapsed or reported
duration (min/hour) and distance (m/km/mi). Sleep accepts a known date or exact
start with an optional end; without an end, duration remains null with partial
coverage. Symptoms are Events with optional linked 0–10 integer severity
Observations. Severity coverage is measured against active same-day symptom
episodes; unrated episodes stay in the denominator, and archived or out-of-day
links do not supply severity. Measurements are Observations for weight (kg/lb),
temperature (C/F), systolic and diastolic pressure (mmHg), and pulse (bpm).
Blood pressure pairs and symptom/severity saves are atomic. The linked severity
Observation is not counted a second time as an unlinked Observation. Manual
source and `user_confirmed` status come from the server; caller-supplied
provenance or broader permissions are not accepted.

The numeric safety ceiling is `1e300` for entered quantities and canonical
conversions. Unit-aware duration/distance validation rejects values that cross
that bound before persistence; this is a software safety limit, not a clinical
limit. The 10,000-object Today cap keeps valid subtotals below IEEE-754 maximum,
and checked conversion and `fsum` reject non-finite values.

The `unit-v1` conversion factors and `today-v1` summary methods are part of
each summary's `method_version`:

| Summary                                 | Method                                                             | Canonical unit      |
| --------------------------------------- | ------------------------------------------------------------------ | ------------------- |
| Meal energy                             | Sum known values                                                   | kcal                |
| Workout duration                        | Sum reported quantity or elapsed interval overlap once per workout | min                 |
| Workout distance                        | Sum known values on workout start day                              | m                   |
| Sleep duration                          | Sum elapsed overlap with the selected day                          | min                 |
| Symptom episodes                        | Count reported symptom Events                                      | episodes            |
| Symptom severity                        | Latest linked severity by local date, instant, then ID             | score               |
| Weight / temperature / pressure / pulse | Latest observation by local date, instant, then ID                 | kg / C / mmHg / bpm |

An omitted optional value remains unknown; it is not zero. A recorded zero is
preserved as zero. Summaries expose `known_value`, canonical `unit`,
`logged_count`, known/total coverage, `partial`, and the versioned method. An
empty metric has a null value and zero counts. Date-only input stores its
entered local date and timezone without a fabricated instant. Exact-time day
bounds are half-open and DST-aware; interval durations use elapsed overlap.
Latest measurements use observed date/time and ID, independent of arrival
order.

The fixed synthetic fixture is 2026-11-01 in `America/Los_Angeles`, a 25-hour
fall-back day (`[2026-11-01T07:00:00Z, 2026-11-02T08:00:00Z)`). Its checked
examples include meal energy `0 kcal` with two meals but one known value
(partial), exercise `90 min` and `1609.344 m` with one of two distances known,
sleep `480 min` allocated by overlap, two symptom episodes with latest severity
5, latest weight `68.0388555 kg`, and `37 C` converted from `98.6 F`. Empty
systolic pressure stays null with zero counts. The domain fixture test checks
values, units, coverage, partial flags and version strings.

Today captures the owner's monotonically increasing daily sequence and
resolves each day candidate's latest Event/Observation revision with a
correlated descending lookup on the owner/object/sequence index. Compound
saves share one sequence and write a marker in the same transaction; a cursor
must refer to a marker. Migration backfill rejects ambiguous intermediate
legacy sequences without deleting history. A PostgreSQL-local two-second
statement timeout bounds pathological revision scans and uses the existing
sanitized 503 response. Timeline and summaries use the same resolved set. Its
opaque cursor binds the
owner, date, timezone, sequence and chronology key; continuation pages do not
repeat Profile context references. Resource list cursors bind the owner,
filters and timezone and order by stable `(created_at, id)` keys. List/history
pages default to 50 and cap at 100; date ranges cap at 366 inclusive days;
cursor text caps at 2,048 characters; compound Add accepts at most 20 events,
20 observations and 20 links; bodies cap at 65,536 bytes. Today returns at most
100 timeline items per page, its indexed candidate set caps at 10,000 objects,
and page one carries at most 100 Profile context references.

## HTTP and generated client contract

OpenAPI is tracked at `contracts/openapi/openapi.json`; generated typed DTOs and
methods live in `packages/api-client/src/generated.ts`. Daily operations are:

| Method               | Route                                    | Operation                                                   |
| -------------------- | ---------------------------------------- | ----------------------------------------------------------- |
| GET / POST           | `/events`                                | `listEvents`, `createEvent`                                 |
| GET / PATCH / DELETE | `/events/{event_id}`                     | `getEvent`, `updateEvent`, `archiveEvent`                   |
| GET                  | `/events/{event_id}/history`             | `listEventHistory`                                          |
| GET / POST           | `/observations`                          | `listObservations`, `createObservation`                     |
| GET / PATCH / DELETE | `/observations/{observation_id}`         | `getObservation`, `updateObservation`, `archiveObservation` |
| GET                  | `/observations/{observation_id}/history` | `listObservationHistory`                                    |
| POST                 | `/daily-entries`                         | `createDailyEntry`                                          |
| GET                  | `/today`                                 | `getToday`                                                  |

Create accepts client IDs so an identical retry returns the existing item;
different content under an already-used ID returns 409. Updates and archive
require `expected_revision`; stale revisions return 409. Foreign and absent
items both return 404. Invalid schema, date range, timezone or cursor returns
422; oversized bodies return 413; storage failures return sanitized 503. Error
responses do not include submitted health values or stack traces.

## Mobile behavior

The home/Profile routes link to Today and Add. Universal Add offers forms for
all five domains, explicit units/time precision and timezone, no numeric zero
defaults, an atomic blood-pressure pair, and linked symptom severity. Date-only
entry does not infer midnight. The Add flow retries uncertain saves with the
original IDs and exact body and blocks edits until recovery. Today supports
date/timezone selection, sparse summary coverage, timeline paging, Profile
context links, loading/empty/error states, refresh and stale in-memory results.
Item screens expose source/revision/time/details, linked severity, edit with
conflict reload, archive confirmation and revision history. Daily edit forms
retain dirty drafts and the original revision across focus refreshes or failed
loads; only a successful explicit reload replaces the baseline. Today blocks
pagination until the current first page succeeds and checks date, timezone,
and sequence before accepting a continuation. The app does not queue offline
writes.

## Validation run

| Check                                         | Result                                                                                                                                                                                                                |
| --------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Review-fix domain suite                       | `pytest -c services/api/pyproject.toml services/api/tests/test_daily_domain.py -q`: 19 passed.                                                                                                                        |
| Current API suite without `TEST_DATABASE_URL` | `pytest -c services/api/pyproject.toml services/api/tests -q`: 39 passed, 40 PostgreSQL-backed tests skipped. New DELETE, sleep, severity, numeric-bound, and snapshot-route regressions are among the skipped tests. |
| Prior P2.2 PostgreSQL validation              | PostgreSQL 16.15 API run: 65 passed; migration upgrade/downgrade/re-upgrade and Alembic drift check passed at `8e31c7c9a0b2`. This validates P2.2 storage/service behavior, not the unrerun P2.3 route suite.         |
| Mobile                                        | Vitest: 54 passed across 11 files; strict app TypeScript and ESLint passed.                                                                                                                                           |
| Client                                        | OpenAPI export and client regeneration passed; the only contract change is the explicit `FiniteDailyNumber` schema alias for daily values. Strict generated-client TypeScript check passed.                           |
| Python static/build                           | Configured CI Ruff check, Ruff format check (36 files), mypy (21 sources), compileall, scaffold verification and Alembic offline SQL generation passed.                                                               |
| Formatting                                    | Whole-repository Prettier check passed after OpenAPI/client regeneration and documentation edits.                                                                                                                     |
| iOS bundle                                    | Expo SDK 57 export succeeded with Node 24.19: 1,136 modules and one 2.5 MB Hermes bundle at `/private/tmp/health-phase2-review-ios-bundle`. This is Metro bundle evidence, not device-interaction evidence.           |
| Migration head                                | `alembic heads`: `b9f5e1a72c4d (head)`. Offline graph/SQL generation passed; database migration lifecycle and model drift checks remain open.                                                                         |

## Main-session final re-review

The eight review findings are addressed and root's code re-review is complete.
A residual numeric-string bypass of the aggregation bound was reproduced and
fixed with a post-coercion magnitude validator; three regressions were added.
The final available Python suite reports **42 passed, 40 PostgreSQL tests
skipped**; mobile reports **54 passed**. Configured CI Python static/scaffold
checks, mobile TypeScript/ESLint and client TypeScript pass. OpenAPI/client
regeneration leaves no tracked diff. These results supersede the earlier
39-pass count above. Phase 2 acceptance remains blocked on the database checks
below; Phase 3 has not started. See `phase-2-review.md` and
`../coordinator-state.md` for the exact resume scope.

## Unverified gates and prerequisites

The documented disposable PostgreSQL 16 cluster at
`/private/tmp/health-phase2-pg-20261003/data` was verified against PID 78748
and its exact PostgreSQL command, then stopped gracefully. Restart and fresh
cluster attempts failed at operating-system shared-memory allocation. No
unrelated process or IPC resource was changed. The exact cluster has no
`postmaster.pid`, `pg_ctl status` reports no server running, and its log ends
with a clean database shutdown. Its failed resume log records
`shmget(key=11678823, size=56)` returning `ENOSPC`; read-only `ipcs -m`
contained no segment with that key. The remaining segments could not be
attributed to this cluster, and a later read-only process inventory showed
other task-owned PostgreSQL clusters, which were left alone. Consequently the P2.3
PostgreSQL-backed route tests, fresh migration lifecycle/drift check, `EXPLAIN`
plans, revision-history worst-case profiling and measured Today latency remain
unverified. The implementation bounds candidate objects at 10,000 and pages
at 100, but those static limits are not a substitute for a database execution
plan or timing result.

During review-fix verification, a new scratch path at
`/private/tmp/health-phase2-review-pg-20261004` was attempted twice with local
PostgreSQL 16.15. Both `initdb` bootstrap attempts failed with `shmget(...,
size=56)` / `ENOSPC`; `initdb` removed the failed data directory. The override
attempt still selected System V shared memory before bootstrap. The sandbox
denied `ps`, and `ipcs -m` displayed no segments while its system query also
reported a permission limitation. No initialized cluster was started, and no
existing or other task-owned PostgreSQL process or IPC resource was touched.
The database-backed tests, migration lifecycle/drift, and query plans were not
run as a result.

PostgreSQL 17/Docker, exact pnpm 9.15 frozen install and the complete GitHub
Actions workflow were unavailable locally. Actual device/simulator keyboard,
visual layout and VoiceOver checks remain manual gates; the iOS bundle verifies
Metro compilation only. Expo's online compatibility endpoint, Phase 0 advisory
and dependency source-use review also remain open. No cloud, AI, future-phase
planning, native health permission or web capability is claimed.

Before a Phase 3 deployment, rerun the complete PostgreSQL 17 CI workflow,
exercise the migration on a fresh database and a backed-up staging copy, run
the P2.3 owner-isolation/snapshot suite, record representative `EXPLAIN
ANALYZE` and bounded Today latency for sparse and high-revision owners, and
complete the device/accessibility and existing Phase 0/1 release gates. Replace
development-only principal/auth settings and configure the approved secure
deployment environment before exposing any health endpoint outside local use.
