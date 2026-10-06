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
