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

## Generation

Run from the repository root after activating the Python 3.12 virtual environment and installing the API development requirements:

```bash
pnpm --filter @personal-health/api-client generate
pnpm --filter @personal-health/api-client typecheck
```

Generation does not connect to the database or cloud. FastAPI exports the OpenAPI JSON, then the repository-owned Node standard-library generator emits client schemas, operation types, and typed fetch methods. It intentionally supports the OpenAPI schema subset used by this service; extend its checks and tests before adding a new construct.
