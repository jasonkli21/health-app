# API layer

HTTP routes, authentication dependencies, typed Profile v1 request/response schemas, and transport concerns only. Route handlers delegate to application commands/queries. Error translation, owner binding, request IDs, body limits and cursor validation stay at this boundary; never accept the owner from request data.

## Optional Assistant boundary

`POST /ai/context` returns a minimized, revision-linked preview scoped to the
authenticated owner. Every included row must be active, valid at the requested
time, in the selected resource types, and explicitly marked
`ai_use_allowed`. Event and Observation candidates use the requested local
lookback window. Safety constraints rank first; the response records bounded
coverage and truncation. Context text and notes are user data and must never be
treated as instructions.

`GET /search` applies PostgreSQL full-text search to current, owner-scoped
resources and enforces the same AI-use permission. Its cursor is bound to the
owner, query and resource filters. A normal Assistant message rebuilds
context before a provider call and validates every returned evidence
reference against the included revisions. No write capability is exposed.

The current adapter is deliberately disabled because the Personal AI service,
service identity, user delegation, tool callback and retention contracts have
not been supplied. `PERSONAL_AI_ENABLED=true` is rejected at configuration
time; there is no configurable destination URL. Context preview and
permission-filtered search work without a provider, while message submission
returns a sanitized 503. This is not evidence of live provider compatibility.
