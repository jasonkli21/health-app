# API contract

FastAPI request and response schemas are authoritative. The tracked, deterministic transport artifact is [`openapi.json`](../../contracts/openapi/openapi.json); TypeScript DTOs and fetch methods are generated from it. Do not maintain handwritten client copies of these schemas.

## Shared behavior

`GET /healthz` is process liveness only and does not query storage. In development mode, owner-scoped routes use the server-configured local principal. In Firebase mode, the API verifies the bearer token and maps the verified issuer and subject to an owner. A missing/disabled local principal, invalid token, or unavailable account returns a sanitized authentication error. Request bodies cannot set an owner, actor, source, lifecycle, or revision; `X-User-ID` and similar client identity headers are ignored.

Every HTTP response includes a server-generated `X-Request-ID`. Errors use `{ "code", "message", "field_errors", "request_id" }`; request validation field errors contain field paths and generic messages, never submitted values. Database failures return a sanitized 503. Request bodies are limited to 65,536 bytes. Profile labels are limited to 120 characters, text values to 2,000, notes to 4,000, metadata to 30 scalar entries and 4,096 encoded bytes, and list/history pages to 100 items.

Times must include a UTC offset and are normalized to UTC. Validity is half-open: `valid_from <= as_of < valid_to`, with either endpoint nullable. Required `profile.value: null` means unknown; it differs from numeric zero and boolean false. A missing PATCH field preserves the stored value, while an explicit null clears optional notes, metadata, or validity endpoints. Profile payload and permission fields reject explicit null. Permission flags default to false.

## Profile v1 routes

| Method and path                                 | Operation ID         | Behavior                                                                                                    |
| ----------------------------------------------- | -------------------- | ----------------------------------------------------------------------------------------------------------- |
| `GET /profile`                                  | `listProfileItems`   | List active, temporally effective items, newest first by stable `(created_at, id)` order.                   |
| `POST /profile`                                 | `createProfileItem`  | Create using a client UUID; identical retry returns the current saved object without reverting later edits. |
| `GET /profile/{item_id}`                        | `getProfileItem`     | Return an owner-scoped item, including archived items.                                                      |
| `GET /profile/{item_id}/history`                | `listProfileHistory` | Return bounded, ascending immutable revisions.                                                              |
| `PATCH /profile/{item_id}`                      | `updateProfileItem`  | Apply a partial update only if `expected_revision` matches.                                                 |
| `DELETE /profile/{item_id}?expected_revision=…` | `archiveProfileItem` | Logical archive; requires the current expected revision.                                                    |

The list supports `as_of` (defaults to server UTC now), `category`, and `limit` (default 50, maximum 100). Its opaque `next_cursor` binds the page position to the configured owner, `as_of`, and category. Use the response `as_of` on later cursor requests. A cursor with a different owner/filter is rejected with 422. Archived objects are omitted from active lists but remain available in owner-scoped detail and history.

Create requires `id` and a typed `profile` object. The server derives owner, manual source, confirmation state, recorded/created/updated timestamps, initial revision and active lifecycle. Optional validity, notes, bounded metadata, and restrictive permission choices are accepted. A first create returns 201; a retry with the same owner, UUID, and canonical content returns 200. Reuse of the UUID with different create content returns 409. The content fingerprint is immutable and excludes later edits.

PATCH requires `expected_revision >= 1` and at least one change. The profile object and temporal validity are validated together before the transaction commits. A stale revision, archived edit, or incompatible create retry returns 409. Unknown or foreign IDs both return 404. Invalid payloads, units, timestamps, page limits, cursors, or schema fields return 422. An unavailable or invalid owner identity returns 401. Request bodies over 65,536 bytes return 413. Database unavailability returns sanitized 503.

The response includes the versioned typed payload; envelope status, title and temporal fields; UTC timestamps; manual-source summary; user-confirmation status; schema version and revision; notes and metadata; and the two restrictive permission flags. Each history entry contains the actor kind, reason, record time, revision, and a typed snapshot. The API does not expose a generic object write route or generic relationship graph endpoint.

## Phase 4 planning and tracker routes

Phase 4 uses the same verified owner dependency and canonical envelope. Create
accepts a client UUID and typed payload; updates and lifecycle transitions
require `expected_revision`; delete is a logical archive. Resource lists are
owner-scoped keyset pages (default 50, maximum 100). A stale resource or
occurrence revision returns 409, invalid fields/references/timezones return
422, and unknown or foreign IDs return 404. Manual saves use the server-owned
`manual` source and `user_confirmed`. AI and cross-domain use permissions
default to false; create and update accept explicit values, return them, and
include them in revision snapshots. Lists omit archived resources by default;
`?archived=true` returns the owner's archived resources.

| Resource | Routes                                                                                                                                          |
| -------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Goals    | `GET, POST /goals`; `GET, PATCH, DELETE /goals/{id}`; `PATCH /goals/{id}/lifecycle`; `GET /goals/{id}/history`                                  |
| Regimens | `GET, POST /regimens`; `GET, PATCH, DELETE /regimens/{id}`; `PATCH /regimens/{id}/lifecycle`; `GET /regimens/{id}/history`                      |
| Plans    | `GET, POST /plans`; `GET, PATCH, DELETE /plans/{id}`; `PATCH /plans/{id}/lifecycle`; `PUT /plans/{id}/items/order`; `GET /plans/{id}/history`   |
| Contexts | `GET, POST /contexts`; `GET, PATCH, DELETE /contexts/{id}`; `PATCH /contexts/{id}/lifecycle`; `GET /contexts/{id}/history`                      |
| Trackers | `GET, POST /trackers`; `GET, PATCH, DELETE /trackers/{id}`; `GET /trackers/{id}/history`; `GET /trackers/{id}/versions?after_version=…&limit=…` |

Lifecycle values are `active`, `paused`, or `completed` for goals, regimens,
and plans; `active` or `ended` for contexts. Tracker definitions are active or
archived. Archival does not delete revisions, tracker schema versions, linked
Observations, or occurrence history. Plan reorder sends the exact ordered item
UUIDs and rejects missing, duplicate, or foreign IDs.

Schedules are edited with `PUT /regimens/{id}/schedule` or
`PUT /plans/{id}/items/{item_id}/schedule`; the matching `GET` paths return the
latest saved definition or null when there is no schedule. Edits include an
explicit effective date and the expected schedule revision. Existing schedules
can only change from a future effective date, preserving earlier versions.
The recurrence `start_date` remains its original alignment anchor when a new
version takes effect. Removing a scheduled plan item retires future intent
without deleting its schedule identity, revisions, or recorded actions.
Occurrence reads use
`GET /regimens/{id}/occurrences` or `GET /plans/{id}/occurrences` with required
`start_date`, `end_date`, and IANA `timezone`; a request spans at most 31 local
calendar dates and returns at most 500 items. `PATCH /plan-occurrences/{key}`
requires the expected schedule and override revisions. Actions are completed,
skipped, or rescheduled. A reschedule supplies an offset-aware instant within
31 days of its original slot; it retains the original occurrence key and
appears on the new due date. Completing or skipping a moved occurrence retains
its moved due instant. Actions may link one existing owner Event or Observation;
this does not create a record. Repeating an identical action is idempotent.
`GET /plan-occurrences/{key}/history` returns owner-scoped, paginated action
revisions, including recorded time, schedule revision, moved time, and linked
record IDs.

`POST /daily-entries` and observation update accept the custom Observation
variant: `{metric: "custom", unit: "custom", tracker_id, schema_version,
values}`. The server resolves the tracker and immutable version for the owner,
rejects malformed or foreign definitions, and validates every field against
that schema. An archived tracker rejects new entries. Historical entries keep
their saved version. Existing numeric daily summaries ignore custom values.

`GET /today` preserves timeline, rollup, and cursor behavior and adds
`plan_items` plus `active_contexts`. Occurrences show their original local slot,
schedule revision, current explicit state, due instant, and DST resolution.
Missing actions are `unknown`; completion is a user assertion and does not
create a health Observation. Contexts are selected by validity date and sorted
by explicit priority then stable ID; they do not change Profile or regimen
state.

## Phase 5 read-only Assistant contracts

Daily Event and Observation create requests accept `ai_use_allowed` (default
`false`); update requests may change it with the current expected revision.
Permission changes are saved in the ordinary revision history. The compound
daily create applies the explicit flag to each submitted object, including
linked severity Observations. Old create retries with permission off retain
their existing idempotency fingerprint behavior. Profile and planning items
already expose the same opt-in; `cross_domain_use_allowed` remains separate
and is not used by this Assistant.

| Route                                      | Contract                                                                                                                                                                                                                                                                                                          |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET /assistant/status`                    | Reports whether a reviewed adapter is ready and which read capabilities are active. Disabled adapters report an empty capability list.                                                                                                                                                                            |
| `POST /ai/context`                         | Builds a current preview for the authenticated owner from `task`, `task_kind`, selected `resource_types`, `lookback_days` (0–90), optional `as_of`/timezone, and optional excluded object UUIDs.                                                                                                                  |
| `GET /search?q=…&types=…&limit=…&cursor=…` | PostgreSQL full-text search over current active resources. `types` is an optional comma-separated list; results require `ai_use_allowed=true`. Limit is 1–50 (default 20); `q` is at most 500 characters.                                                                                                         |
| `POST /assistant/messages`                 | Accepts an 8,000-character message and the same scope request. Health checks adapter availability before building or sending context; the current disabled adapter returns sanitized 503. A configured adapter must receive a newly built Pack and return evidence references that resolve to included revisions. |

The Pack v1 includes the task and selected types, random per-request opaque
owner scope, timezone and `as_of`, revision-linked minimized entries,
source/confirmation metadata, inclusion counts, user exclusions, deterministic
truncation and a 65,536-byte serialized budget. Current-day rollups are
calculated only from included, opted-in Event/Observation entries and explicitly
label their coverage as that included subset. Profile constraints rank first;
active contexts, goals/preferences, facts, and recent daily records follow.
Eligible safety constraints that cannot fit cause 422 rather than silent
omission. Text and notes are untrusted user data. Plan and context references
remain only when the target also appears in the Pack; other history, trackers,
trends, records, or arbitrary database results are excluded.

Search and context filter by authenticated owner, active status, temporal
validity, selected resource type, and per-object AI permission. Daily search
uses a bounded 90-day local window; context uses the requested local-day
window. Full-text search uses additive GIN indexes on envelope title/notes and
typed JSON payloads (migration `f5c0a1e2d3b4`). Cursors bind to owner, query and
resource filters. Provider callbacks and service delegation are not available
until an actual Personal AI protocol is supplied and reviewed.

## Phase 6 typed action proposals

Action proposals use dedicated owner-scoped tables and never appear as
canonical health objects before apply. The owner-authenticated endpoint may
create an owner-authored draft; it does not accept an AI source, service
credential, actor ID, or owner ID from the request. The Phase 5 Personal AI
adapter remains disabled, and no `health.propose.*` service tool is registered
until a real service identity, delegated-user capability, callback, and
retention contract are supplied.

| Method and path                                  | Operation                   | Behavior                                                                                                                                                                                                                                                                              |
| ------------------------------------------------ | --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `POST /action-proposals`                         | `createActionProposal`      | Create an idempotent pending proposal with 1–10 typed commands, at most 20 evidence refs, rationale up to 1,000 characters, and a 65,536-byte request/content bound. A server-configured lifetime defaults to 24 hours and is capped at 7 days. Target IDs are stable after creation. |
| `GET /action-proposals?state=…&limit=…&cursor=…` | `listActionProposals`       | Owner-scoped keyset page (default 50, max 100); cursor binds to owner and state filter.                                                                                                                                                                                               |
| `GET /action-proposals/{id}`                     | `getActionProposal`         | Return the current immutable proposal revision, hash, source, evidence labels/revisions, validation summary, state, and applied result IDs/revisions.                                                                                                                                 |
| `GET /action-proposals/{id}/history`             | `listActionProposalHistory` | Return bounded append-only created/edited/applied/rejected/expired events.                                                                                                                                                                                                            |
| `PATCH /action-proposals/{id}`                   | `editActionProposal`        | Replace the reviewed typed content only while pending and with the expected proposal revision. Appends a new immutable revision and hash.                                                                                                                                             |
| `POST /action-proposals/{id}/apply`              | `applyActionProposal`       | Require `{proposal_revision, content_hash, idempotency_key, confirmation: "explicit_user_save"}` and a verified owner identity. Replays the saved result for the same proposal revision.                                                                                              |
| `POST /action-proposals/{id}/reject`             | `rejectActionProposal`      | Reject the exact current pending revision, with an optional reason up to 500 characters.                                                                                                                                                                                              |

The closed command union supports Profile create/update, Event create with
explicitly linked supported Observations, goal create/update, plan
create/update, and tracker-definition create. Commands reuse existing typed
schemas and application commands. They cannot archive/delete, edit AI or
cross-domain permissions, grant authorization, or use unrestricted patches.
Updates include an expected target revision. Evidence must resolve to an
owner object and its current revision on creation and apply. Foreign IDs remain
indistinguishable from unknown IDs.

Plan commands can reference existing owner Goals and Regimens. A Plan in the
same proposal may reference a `goal.create` command only when that command
appears earlier in the declared command order. Create IDs are stable across
retries and edits that retain the command's position and action; the returned
Goal ID can then be used when a Plan is added to a later revision. References
to later commands and cycles are rejected.

Apply locks the proposal row and runs all commands, source/history changes,
proposal state/event, target `health_object_revisions`, and command receipt in
one transaction. A target conflict rolls back every target write and leaves
the proposal pending with a sanitized validation summary. Receipt uniqueness
is `(owner_id, idempotency_key)` and
`(owner_id, proposal_id, proposal_revision)`. Reusing a key with different
content returns 409; a stale proposal revision/hash returns 409; expiry is
checked at apply and returns 410. Validation errors return 422, missing or
foreign proposals return 404, and database failures return sanitized 503.
Target history includes `proposal_id`; applied objects preserve the proposal
origin and `user_confirmed` status.

The mobile Assistant shows command fields, time/units, evidence and expiry.
Editing the typed command text creates a new revision; users must confirm that
new revision. The deliberate `Confirm and save` action is the confirmation for
that displayed revision; the executor does not open a redundant confirmation
dialog. Current AI generation remains unavailable under the Phase 5 external
integration gate.

## Generation

Run from the repository root after activating the Python 3.12 virtual environment and installing the API development requirements:

```bash
pnpm --filter @personal-health/api-client generate
pnpm --filter @personal-health/api-client typecheck
```

Generation does not connect to the database or cloud. FastAPI exports the OpenAPI JSON, then the repository-owned Node standard-library generator emits client schemas, operation types, and typed fetch methods. It intentionally supports the OpenAPI schema subset used by this service; extend its checks and tests before adding a new construct.

### Occurrence history and action eligibility

Recorded occurrences retain their original schedule revision and remain visible
in Today after schedule edits, item retirement, or parent lifecycle changes.
`can_act` indicates whether the current parent/item state permits another action;
historical occurrences remain readable when it is false. A moved due instant
remains the display instant after completion or skipping. PATCH association
fields omitted together preserve an existing Event/Observation link; explicitly
supplying null clears it. Existing recorded slots use their immutable schedule
revision for subsequent actions, with optimistic occurrence revision checks.
