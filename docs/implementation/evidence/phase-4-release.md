# Phase 4 release evidence

**Checkpoint:** October 5, 2026; local implementation and static review are
complete, with database, cloud, and device acceptance gates still open.

## Implemented surface

Phase 4 adds owner-scoped goals, regimens, plans, contexts, and custom tracker
definitions to the existing health object, source, revision, and history model.
Migration `d4e5f607a8b9` follows `c3721f5a9a01`. It adds planning resources,
stable plan links and regimen schedule identities, effective schedule versions,
occurrence overrides/actions, tracker schema versions, and custom tracker
references/values on Observations. The downgrade refuses to drop Phase 4 data.

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
resources have read-only detail. Today shows active contexts and scheduled
occurrences with explicit complete, skip, and reschedule actions; conflicts
refresh the current data. Universal Add links to custom tracker logging.
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

The following static checks passed after the final source edits:

- `.venv/bin/python -m compileall -q services/api/src migrations`
- `.venv/bin/mypy services/api/src/health_api` — 28 source files
- `.venv/bin/ruff check` and `.venv/bin/ruff format --check` on changed API and
  migration Python files
- `pnpm --filter @personal-health/api-client typecheck`
- `pnpm --filter @personal-health/mobile typecheck`
- `pnpm --filter @personal-health/mobile lint`
- OpenAPI export and API client regeneration
- `git diff --check`

No tests were added or run. Static checks and generated contracts do not prove
database behavior, cloud parity, or device behavior.

## Open acceptance gates

- **Database:** Phase 2 PostgreSQL acceptance is still open. The Phase 4
  migration has not been applied to a live disposable database in this
  checkpoint; upgrade/downgrade/re-upgrade, constraint behavior, model drift,
  query plans, and current query-cost measurements remain unverified. The
  prior attempt to create a disposable PostgreSQL cluster is documented in the
  Phase 2 coordinator history and was blocked by host shared-memory exhaustion.
- **Cloud:** Phase 3 live auth, storage, migration, rollback, and staging parity
  remain unverified. No cloud resources or user data were accessed for this
  implementation.
- **Mobile:** Simulator/device layout, real timezone and DST presentation,
  keyboard navigation, VoiceOver, and end-to-end session/error behavior remain
  manual review items. This checkpoint did not run a mobile bundle or test
  suite.

## Future context-builder inputs

Phase 6 may consume active contexts together with their validity window,
explicit priority, typed links, and user-authored notes. It may also consume
scheduled intent separately from occurrence action state and actual Events or
Observations. Preserve unknown state and provenance; these records express
user intent and self-report, not clinical truth, adherence, or inferred
progress. Context must not silently override Profile or pause a regimen.
