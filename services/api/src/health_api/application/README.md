# Application layer

`profile_service.py` owns transactional create/retry/update/archive/history and
owner-filtered queries. It resolves the configured manual source, stores the
validated subtype together with its common envelope, and appends one snapshot
per revision in the same transaction. Revision locks reject stale edits rather
than merging them. `local_principal.py` resolves only the server-configured
local user; request data never supplies an owner. Keep route handlers thin and
translate application errors only at the API boundary.

`action_proposal_service.py` stores strict command drafts separately from
canonical health facts. It revalidates evidence and target revisions, then
composes existing domain commands inside one outer transaction. `unit_of_work`
uses savepoints when a command is composed, so the caller retains commit and
rollback ownership. Applied target histories record the proposal ID and
confirmed owner; the command receipt, proposal event, target writes and
histories share the same commit boundary. Proposal creation from a Personal AI
service remains disabled until that service's identity and delegated-user
contract is supplied.

Daily commands in `daily_service.py` share a committed owner sequence across
every Event and Observation in one compound save. `today_service.py` resolves
the latest revision for each day candidate through the owner/object/sequence
index and builds summaries from that same snapshot. The PostgreSQL read uses a
transaction-local two-second statement timeout; compound snapshot markers keep
continuation cursors on complete command boundaries.

`ai_context_service.py` builds local previews and search results from
owner-scoped canonical rows. Each request rechecks item permission, active
state, temporal validity, selected resource types/domains/sections, and any
request-specific exclusions. Request scope can narrow sharing but cannot
grant it. Ranking is deterministic and the serialized pack has entry and byte
bounds; mandatory constraints that cannot fit cause a validation error.
Relationship references are retained only when both permitted endpoints are
included. Today summaries use only the included permitted Events and linked
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

`analytics_service.py` loads owner-scoped active Event/Observation inputs once
per multi-metric request, with a 366-day window, 10,000 total source-row cap,
and PostgreSQL statement timeout. It delegates daily units/time overlap to the
Phase 2 rollup, persists signals and user-reviewed artifacts in the canonical
Health object/history system, and links exact source revisions through
`analytics_evidence`. Daily edits and archives invalidate dependent snapshots
inside their write transaction; new daily input conservatively stales current
analytics so an on-demand recompute cannot miss it. Insight/recommendation
expiry is enforced on reads and actions. Recommendation acceptance records
interest only; the sole v1 suggestion is to continue logging and creates no
health write or action proposal. Experiments are user-authored, revisioned,
editable as drafts; once started, the outcome design stays fixed while notes
remain editable. Starting requires a known baseline value. Lifecycle changes
are manual, and results are descriptive baseline/intervention summaries.

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
