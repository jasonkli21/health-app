# Application layer

`profile_service.py` owns transactional create/retry/update/archive/history and
owner-filtered queries. It resolves the configured manual source, stores the
validated subtype together with its common envelope, and appends one snapshot
per revision in the same transaction. Revision locks reject stale edits rather
than merging them. `local_principal.py` resolves only the server-configured
local user; request data never supplies an owner. Keep route handlers thin and
translate application errors only at the API boundary.
