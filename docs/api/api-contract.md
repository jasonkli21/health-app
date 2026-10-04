# API contract

FastAPI request and response schemas are authoritative. The tracked, deterministic transport artifact is [`openapi.json`](../../contracts/openapi/openapi.json); TypeScript DTOs and fetch methods are generated from it. Do not maintain handwritten client copies of these schemas.

## Shared behavior

The API is a private local-development service. `GET /healthz` is process liveness only and does not query storage. Profile routes use one server-configured local principal. A missing or disabled principal returns 401. Request bodies cannot set an owner, actor, source, lifecycle, or revision; `X-User-ID` and similar client identity headers are ignored. There is no internet authentication in this phase.

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

PATCH requires `expected_revision >= 1` and at least one change. The profile object and temporal validity are validated together before the transaction commits. A stale revision, archived edit, or incompatible create retry returns 409. Unknown or foreign IDs both return 404. Invalid payloads, units, timestamps, page limits, cursors, or schema fields return 422. Missing local principal returns 401. Request bodies over 65,536 bytes return 413. Database unavailability returns sanitized 503.

The response includes the versioned typed payload; envelope status, title and temporal fields; UTC timestamps; manual-source summary; user-confirmation status; schema version and revision; notes and metadata; and the two restrictive permission flags. Each history entry contains the actor kind, reason, record time, revision, and a typed snapshot. The API does not expose a generic object write route or generic relationship graph endpoint.

## Generation

Run from the repository root after activating the Python 3.12 virtual environment and installing the API development requirements:

```bash
pnpm --filter @personal-health/api-client generate
pnpm --filter @personal-health/api-client typecheck
```

Generation does not connect to the database or cloud. FastAPI exports the OpenAPI JSON, then the repository-owned Node standard-library generator emits client schemas, operation types, and typed fetch methods. It intentionally supports the OpenAPI schema subset used by this service; extend its checks and tests before adding a new construct.
