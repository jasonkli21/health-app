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
