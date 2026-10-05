# Phase 4 release evidence

**Checkpoint:** October 5, 2026; phase 4 review corrections are implemented
and locally verified, with database, cloud, and device acceptance gates still
open.

## Implemented surface

Phase 4 adds owner-scoped goals, regimens, plans, contexts, and custom tracker
definitions to the existing health object, source, revision, and history model.
Migration `d4e5f607a8b9` follows `c3721f5a9a01`. It adds planning resources,
stable plan links and regimen schedule identities, effective schedule versions,
occurrence overrides/actions, tracker schema versions, and custom tracker
references/values on Observations. The downgrade refuses to drop Phase 4 data.

Migration `a7f014edc620` follows `d4e5f607a8b9` and preserves retired schedule
identity, original occurrence timing and DST resolution, and optional
Observation links for occurrence actions. Its downgrade refuses to discard
review-correction data. ORM relationships now select the Observation envelope
foreign key explicitly, and absent tracker JSON binds as SQL `NULL`.

Resource lists use owner-scoped cursor pagination (default 50, maximum 100).
Create is idempotent for the same owner, UUID, and canonical content. Resource
updates and lifecycle changes use optimistic revisions; archive is logical.
Goals, regimens, and plans support active/paused/completed/archived states;
contexts support active/ended/archived; trackers support active/archived.
Foreign and unknown IDs resolve to the same 404. Plan reorder requires the
complete ordered set of stable item IDs. Contexts are selected by validity and
explicit priority; they do not mutate Profile or regimen state.

The API exposes typed CRUD, lifecycle and history routes for each resource
group. Plans also expose item reorder. Tracker history and immutable schema
versions have dedicated reads. Schedule reads and writes are available for a
regimen or plan item. Occurrences are queried for explicit date ranges and an
IANA timezone; updates require expected schedule and occurrence revisions.
`GET /today` adds `plan_items` and `active_contexts` without changing daily
timeline, rollup, or cursor semantics. Route details and error behavior are in
the [API contract](../../api/api-contract.md#phase-4-planning-and-tracker-routes).

## Schedule and occurrence rules

- Recurrence is bounded to daily or weekly rules. Expansion accepts up to 31
  local calendar dates and returns at most 500 items.
- Schedule edits are effective-dated. Existing definitions can only be changed
  from a future effective date, retaining earlier schedule versions.
- An occurrence key identifies the original slot from its resource/item,
  schedule identity, local date, and local time. Rescheduling retains that key
  and displays the occurrence on its new due date.
- Spring-forward gaps resolve to the next valid local minute. Fall-back overlap
  resolves once using the earlier offset. The response records the resolution.
- Actions are completed, skipped, or rescheduled. A reschedule requires an
  offset-aware instant within 31 days of the original slot. Identical retries
  are idempotent; stale schedule/action revisions conflict. Completion is an
  explicit user assertion and creates no Event or Observation.
- Recorded assertions retain their occurrence key, original timing and
  timezone across schedule edits, parent lifecycle changes, and item
  retirement. A moved due instant remains attached after completion or skip.
  Legacy assertions without the new timing fields are reconstructed from their
  immutable schedule revision. Owner-scoped paginated action history is
  available by occurrence key.
- Occurrences without an action remain `unknown`; the service does not infer
  adherence or missed activity.

## Tracker schema and logging rules

Tracker definitions use stable field IDs and immutable numbered schema
versions. Supported fields are bounded primitive text, number, boolean, enum,
date, and quantity values. Schema edits create a new version; saved entries
continue to reference their original tracker and schema version. New entries
for archived trackers are rejected, while historical entries remain readable.

Custom values are stored on the existing Observation envelope with tracker ID,
schema version, and values keyed by field ID. The service verifies ownership,
version, field identifiers, required fields, and value types. Missing optional
fields remain absent; explicit `false` and `0` are preserved. Existing numeric
daily rollups ignore custom metrics. Historical display resolves field labels
from the entry's saved schema version.

## Mobile implementation

The Plan surface groups goals, regimens, plans, contexts, and trackers. It
supports create/edit/detail/history and lifecycle actions, plan item ordering,
schedule editing, and context links to Profile, goals, and regimens. Archived
resources have read-only detail and can be rediscovered from the archived list;
ended contexts remain visible. List and reference pickers expose user-driven
pagination. Today shows active contexts and scheduled occurrences with explicit
complete, skip, reschedule, and optional existing Event/Observation association
actions. Conflicts refresh current data while preserving drafts. Universal Add
links to custom tracker logging. Create recovery keeps the original ID and
request across uncertain responses and is scoped to the session owner and
epoch. Late responses cannot restore another account's recovery state.
Tracker forms use the active schema and the existing uncertain-save recovery
path. Historical custom observations display labels from the exact saved
schema version and cannot be edited through the standard Observation editor.

## Contract generation and local verification

OpenAPI JSON and the generated TypeScript client are committed together. The
generation command used was:

```bash
CI=true PATH="/Users/jasonkli/projects/health-app/.venv/bin:/Users/jasonkli/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH" \
  pnpm dlx pnpm@9.15.0 --filter @personal-health/api-client generate
```

The following local checks passed after the final source edits:

- API suite: `.venv/bin/python -m pytest services/api/tests -q` — **99 passed,
  43 skipped**. Thirteen focused regressions cover mapper setup, SQL NULL
  binding, schedule anchor edits, strict occurrence-key parsing, historical
  occurrence timing, resource eligibility, permission defaults, association
  contracts, range and numeric overflow, and repeated plan references.
- Mobile suite: bundled Node `vitest.mjs run` — **87 passed across 18 files**.
  Added focused session-recovery, uncertain planning-create, tracker input, and
  stable field-ID coverage.
- Mobile TypeScript: `tsc --noEmit` — passed.
- Mobile ESLint — passed with no warnings.
- API typing: `.venv/bin/mypy services/api/src/health_api` — passed for 28
  source files.
- `.venv/bin/ruff check`, `.venv/bin/ruff format --check`, and Python
  `compileall` on changed API, test, and migration files — passed.
- Prettier check on changed mobile/client files — passed.
- OpenAPI export and TypeScript client regeneration — passed; generated files
  are committed with their source contract.
- `git diff --check` — passed.

The API run skipped 43 database-dependent tests because no `TEST_DATABASE_URL`
was supplied. Local tests and generated contracts do not prove database
behavior, cloud parity, or device behavior.

## Open acceptance gates

- **Database:** Phase 2 PostgreSQL acceptance is still open. The Phase 4
  migrations have not been applied to a live disposable database in this
  checkpoint; upgrade/downgrade/re-upgrade, constraint behavior, model drift,
  query plans, and current query-cost measurements remain unverified. The
  prior attempt to create a disposable PostgreSQL cluster is documented in the
  Phase 2 coordinator history and was blocked by host shared-memory exhaustion.
- **Cloud:** Phase 3 live auth, storage, migration, rollback, and staging parity
  remain unverified. No cloud resources or user data were accessed for this
  implementation.
- **Mobile:** Simulator/device layout, real timezone and DST presentation,
  keyboard navigation, VoiceOver, and end-to-end session/error behavior remain
  manual review items. This checkpoint did not run a mobile bundle or device
  acceptance scenario; the automated mobile suite ran as listed above.

## Future context-builder inputs

Phase 6 may consume active contexts together with their validity window,
explicit priority, typed links, and user-authored notes. It may also consume
scheduled intent separately from occurrence action state and actual Events or
Observations. Preserve unknown state and provenance; these records express
user intent and self-report, not clinical truth, adherence, or inferred
progress. Context must not silently override Profile or pause a regimen.

## Follow-up audit of `80a8c96`

See [independent audit evidence](phase-4-audit.md) for additional corrections,
current verification counts, and open acceptance gates.
