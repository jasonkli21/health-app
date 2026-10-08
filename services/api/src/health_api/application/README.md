# Application layer

`profile_service.py` owns transactional create/retry/update/archive/history and
owner-filtered queries. It resolves the configured manual source, stores the
validated subtype together with its common envelope, and appends one snapshot
per revision in the same transaction. Revision locks reject stale edits rather
than merging them. `local_principal.py` resolves only the server-configured
local user; request data never supplies an owner. Keep route handlers thin and
translate application errors only at the API boundary.

Planning application work stays behind `planning_service.py`, the stable
route-facing façade. `planning_resources.py` owns resource CRUD, references,
revision history, and plan ordering. `planning_schedules.py` owns effective-
dated schedule revisions, recurrence and occurrence identity, rescheduling,
and the Today planning read. `planning_trackers.py` owns immutable tracker
schema history and validation of custom tracker entries. The caller owns each
write transaction; schedule edits lock the parent resource, while tracker
entry validation locks its tracker row and keeps that lock through the caller's
transaction.

Proposal application stays behind `action_proposal_service.py`, the stable
route-facing façade. `proposal_support.py` owns canonical snapshots, revision
state, and review summaries. `proposal_validation.py` validates typed commands,
evidence, and target revisions and builds before/after previews without
mutating canonical state. `proposal_lifecycle.py` owns owner-authored create,
read, edit, reject, expiry, and history behavior. `proposal_apply.py` owns
exact confirmation, target locks, command execution, transactional receipts,
and idempotent replay. Apply locks the owner first, then referenced health
objects in sorted ID order; composed writes use savepoints so the outer apply
transaction owns commit and rollback. Proposal creation from a Personal AI
service remains disabled until that service's identity and delegated-user
contract is supplied.

Daily commands in `daily_service.py` share a committed owner sequence across
every Event and Observation in one compound save. `today_service.py` resolves
the latest revision for each day candidate through the owner/object/sequence
index and builds summaries from that same snapshot. The PostgreSQL read uses a
transaction-local two-second statement timeout; compound snapshot markers keep
continuation cursors on complete command boundaries.

`ai_context_service.py` is the stable preview/search façade.
`ai_context_admission.py` is the single SQL admission gate for owner, item
permission, active/current state, temporal validity, supported type, selected
domain, request exclusions, and hidden custom tracker values.
`ai_context_projection.py` maps admitted rows to local preview/search fields
and removes relationship endpoints that are not also included.
`ai_context_ranking.py` owns PostgreSQL text ranking and deterministic order;
`ai_context_search.py` owns bounded search pagination.
`ai_context_pack.py` owns Today/trend assembly, entry and byte budgets, and
truncation metadata. Request scope only narrows eligible sharing; it cannot
grant item permission. The cross-domain flag remains separate and does not
grant AI use. Today summaries use only included permitted Events and linked
Observations, so truncation or scope cannot reveal a withheld endpoint.

The custom-tracker Observation value is excluded from AI context and search
until its immutable tracker schema can be included safely for interpretation.
Scheduled occurrence intent is also not part of the current context pack.
Search uses a permission-safe text projection, including during matching and
ranking, rather than sanitizing only displayed excerpts. Preview and search
are Health-side capabilities; sending a live message remains disabled until
the external Personal AI identity, delegation, callback, and retention
contract is reviewed. Focused API coverage lives in
`services/api/tests/test_ai_context_api.py`; PostgreSQL-specific cases still
require the documented disposable test database.

`analytics_service.py` keeps the route-facing operations stable.
`analytics_sources.py` loads owner-scoped current Event/Observation inputs and
revision/provenance evidence once per request, with a 366-day window, 10,000
total source-row cap, and PostgreSQL statement timeout. Its typed source
snapshot also captures the owner generation used by the calculation.
`analytics_computation.py` derives deterministic metric points from that
snapshot without a database session. `analytics_artifacts.py` persists signals
and user-reviewed artifacts in the canonical Health object/history system,
links exact source revisions through `analytics_evidence`, and revalidates the
owner generation and evidence revisions before commit. Daily edits and
archives invalidate dependent snapshots inside their write transaction; new
daily input conservatively stales current analytics so an on-demand recompute
cannot miss it. Insight/recommendation expiry is enforced on reads and
actions. Recommendation acceptance records interest only; the sole v1
suggestion is to continue logging and creates no health write or action
proposal. Experiments are user-authored, revisioned, editable as drafts; once
started, the outcome design stays fixed while notes remain editable. Starting
requires a known baseline value. Lifecycle changes are manual, and results
are descriptive baseline/intervention summaries.

`healthkit_import_service.py` validates one bounded type-specific batch before
entering an owner-locked unit of work. Batch receipts and canonical daily
Event/Observation writes commit together; source identities make retries and
changed samples deterministic. Aggregate revisions reject stale updates and
allow recomputation only after a newer revision follows deletion. Sample
tombstones persist even before a sample is first imported. Device imports stay
unconfirmed and AI use disabled; user archives and manual corrections remain
protected from source updates. Shared daily rollups apply the same aggregate,
sleep, and manual-precedence rules to Today, analytics, and consent-filtered
context. Today holds a shared owner lock across cursor validation and snapshot
loading while preference changes take the conflicting update lock.
