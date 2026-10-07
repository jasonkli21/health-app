# API layer

HTTP routes, authentication dependencies, typed Profile v1 request/response schemas, and transport concerns only. Route handlers delegate to application commands/queries. Error translation, owner binding, request IDs, body limits and cursor validation stay at this boundary; never accept the owner from request data.

`analytics.py` exposes the Phase 7 metric and pair catalogs, bounded trend and
association reads, insight refresh/list/detail/dismissal, recommendation
list/detail/acceptance/dismissal, and manual experiment CRUD/lifecycle/results.
All routes use the verified owner dependency. List cursors bind to owner and
filters; write actions use expected artifact revisions. Numerical outputs carry
method version, coverage, unit, window, and source evidence; they do not assert
diagnosis or causation.

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
reference against the included revisions. No provider write capability is exposed.

The current adapter is deliberately disabled because the Personal AI service,
service identity, user delegation, tool callback and retention contracts have
not been supplied. `PERSONAL_AI_ENABLED=true` is rejected at configuration
time; there is no configurable destination URL. Context preview and
permission-filtered search work without a provider, while message submission
returns a sanitized 503. This is not evidence of live provider compatibility.

Phase 7 permits a `trends` context section with one selected metric, only when
both Event and Observation types are in scope and the request has no domain
filter. Health recomputes the summary from current `ai_use_allowed` rows;
numeric tracker metrics also require their active tracker definition to be
AI-permitted. This remains a local preview capability while the provider is
disabled.

## Typed action proposals

`/action-proposals` is an owner-authenticated review API. Its draft endpoint
accepts only bounded typed Profile create/update, Event create with linked
supported Observations, goal create/update, plan create/update, and tracker
definition create commands. The server assigns stable target IDs when it saves
the first proposal revision. Permission grants, archive/delete, arbitrary
patches, service identities, and caller-supplied source/actor metadata are not
accepted.

The route can create an owner-authored pending proposal, but there is no
Personal AI service submission route or delegated `health.propose.*` tool in
this build. The provider remains disabled. Apply and reject always use the
verified owner dependency. Apply requires the exact proposal revision and
content hash plus `confirmation: explicit_user_save`; retries replay a durable
owner-scoped command receipt. See the root API contract and Phase 6 release
evidence for all fields and current external gates.

## Optional HealthKit import

`healthkit_imports.py` exposes owner-authenticated normalized batches,
receipts, status, and aggregate source preferences. The route accepts no
caller owner ID or native anchor; all transaction and dedupe behavior stays in
the application service. Batch bodies have a 1 MiB route limit and strict
schema/resource bounds. The server accepts minimal allowlisted normalized
metadata only; it does not accept raw HealthKit samples or grant AI-use
permission. See the root API contract and Phase 8 evidence for the incomplete
native/device gates.
