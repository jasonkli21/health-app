# Application layer

`profile_service.py` owns transactional create/retry/update/archive/history and
owner-filtered queries. It resolves the configured manual source, stores the
validated subtype together with its common envelope, and appends one snapshot
per revision in the same transaction. Revision locks reject stale edits rather
than merging them. `local_principal.py` resolves only the server-configured
local user; request data never supplies an owner. Keep route handlers thin and
translate application errors only at the API boundary.

Daily commands in `daily_service.py` share a committed owner sequence across
every Event and Observation in one compound save. `today_service.py` resolves
the latest revision for each day candidate through the owner/object/sequence
index and builds summaries from that same snapshot. The PostgreSQL read uses a
transaction-local two-second statement timeout; compound snapshot markers keep
continuation cursors on complete command boundaries.
