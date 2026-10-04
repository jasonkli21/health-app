# Phase 1 — Canonical health model and Profile

## Implementation-time reconciliation gate

**Status: reconciled for implementation on 2026-10-03.** The user explicitly requested implementation of Phases 1–9 sequentially, so that instruction authorizes this Phase 1 work under the `CODEX.md` exception; the original Phase 0-only handoff is superseded for this run. Read the roadmap, CODEX, Phase 0 review, product/security/architecture/data/API/local-development docs, all accepted ADRs 0001–0007, phase-plan standard and all phase plans. The actual tree matched the documented Phase 0 baseline: only the Expo shell, FastAPI liveness route, placeholder client-generation command, README-only migration/layer directories, and liveness test existed. There was no product data contract or preceding release to preserve. Python 3.12 and Node 24.19 are available through the bundled runtimes; the exposed pnpm fallback is 11.19 even though the repository pins 9.15.0. Docker is absent. PostgreSQL 16 server/client tools are installed. The unprivileged temporary-cluster initialization was denied shared-memory access; an approved disposable PostgreSQL 16 cluster is now running on a private Unix socket under `/private/tmp/health-phase1-pg`. PostgreSQL 17 Docker execution and an actual iOS simulator/device walkthrough remain external gates. The existing Starlette/httpx warning and dated Phase 0 advisory inventory remain review gates; no dependency advisory is treated as resolved merely by scaffold checks.

Reconciled implementation choices: use the already-established root `migrations/` directory for Alembic; retain synchronous SQLAlchemy 2/psycopg and the PostgreSQL JSONB contract; create only the six Phase 1 tables in this plan; make the configured server-side `LOCAL_PRINCIPAL_ID` the only local identity input and return 401 when it is absent; store payloads and revisions atomically with composite owner-scoped foreign keys; and keep relationships as a narrow service capability without a generic graph endpoint. Keep schema/client artifacts tracked and deterministically generated from FastAPI OpenAPI. **Generator deviation:** `pnpm view` could not resolve `registry.npmjs.org` and no OpenAPI generator exists in the installed pnpm store. To avoid inventing an unverified lock entry or making generation depend on unavailable network access, Phase 1 will use a small repository-owned Node standard-library generator for the OpenAPI schema subset emitted by this service. It emits both OpenAPI-derived DTO/operation types and typed fetch methods; CI will regenerate and check for drift. This adds a maintenance responsibility: a later API schema construct outside the tested OpenAPI subset must extend the generator before use. The mobile component-test runner remains to be selected against the installed/runtime constraints before its first use. Continue to preserve all later-phase boundaries. No accepted ADR or Phase 1 data semantics are changed by this reconciliation.

The existing baseline is `apps/mobile/app/{_layout,index}.tsx`, reserved `apps/mobile/src`/`tests`, `services/api/src/health_api/{api,application,domain,persistence,integrations,config}` README layers, liveness `main.py`, `services/api/tests/test_smoke.py`, root `migrations/`, `contracts/openapi/`, and workspace placeholder `packages/api-client`. `packages/domain`, `design-tokens`, `shared` contain only READMEs. **Every artifact below beyond that baseline is planned/provisional.** This plan supplies execution choices that must be ratified at reconciliation, not claims about existing contracts.

## Outcome and boundary

**Deliver:** durable owner-scoped canonical objects, sources, profile facts/constraints/preferences, relationships, versioned validation, temporal revisions, local principal boundary, real generated client, and a small usable Profile slice. A user can create optional items, inspect provenance/history, edit with conflict detection and archive them.

**Defer:** Events/Observations/Today/Add to Phase 2; real shared identity/cloud to Phase 3; goals/regimens/plans/contexts/trackers to Phase 4; all AI to Phase 5 onward; device imports/records/web. Do not precreate empty subtype tables for later phases or a five-tab shell of fake products.

## Canonical model contract

Use UUID identities and timezone-aware UTC persisted instants. No database credentials reach the client. One internal `users`/principal row owns all data; provider identity maps to it later rather than changing object owner IDs. Local dev principal is explicitly configured, server-controlled, and allowed only with local environment/dev auth. Never accept `owner_id` from mobile body or arbitrary headers. Phase 1 is private local development, not an internet-authenticated release.

| Planned persistence       | Required contract                                                                                                                                                                                                                                                       |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `users`                   | UUID primary key; non-sensitive display settings including IANA timezone; lifecycle; local identity mapping isolated from health payloads                                                                                                                               |
| `sources`                 | Owner, source kind (`manual`, `device`, `document`, `provider`, `ai`, `system`), optional external namespace/identifier, recorded timestamp; Phase 1 creates manual sources only                                                                                        |
| `health_objects`          | ID, owner, object_type, domain, status (`active`/`archived`), title, valid_from/valid_to, recorded_at/created_at/updated_at, source_id, confirmation_status, schema_version, revision integer, notes and bounded metadata JSONB; source and owner composite consistency |
| `profile_items`           | One-to-one owner-consistent envelope; kind fact/constraint/preference, category/key, validated versioned payload; relational category/kind/key for queries                                                                                                              |
| `health_object_revisions` | Append-only snapshots of envelope/subtype payload, revision, server timestamp, actor kind/ID, reason; initial creation included; no payloads in routine logs                                                                                                            |
| `health_relationships`    | Owner-scoped directed endpoints, typed relation (`related_to` initially), source and validity; validate both endpoints belong to owner; no dangling/cross-owner edges                                                                                                   |

Use DB foreign keys/checks/unique keys and application validation together. `valid_from` and `valid_to` are optional effective instants, with half-open interval `[from,to)` and `from < to` if both supplied; null bound means unbounded, not an invented date. Recorded time is when knowledge entered Health, distinct from validity. Updates do not overwrite previous history. Current profile query includes active items whose effective window includes `as_of`; unknown/unbounded validity is labeled accordingly. History can reconstruct old revisions; do not imply a complete bitemporal query engine.

A versioned registry in planned `domain/schemas.py` maps `(object_type, schema_version)` to Pydantic models. Start only with Profile v1, reject unknown versions/extra unrecognized fields and bound text/metadata sizes. Profile v1: `kind`, stable category (`background`, `constraints`, `preferences`), user-facing label/key and typed `value` union (text, boolean, number, quantity, text-list). Category/kind compatibility is explicit; no clinical diagnosis/inference or exhaustive questionnaire. A nullable value is unknown, `false` and `0` are valid known values; quantities carry finite numeric value and supported unit. Preserve user-provided text without treating it as executable markup. Metadata is not an escape hatch for invalid health payloads. Constraints/preferences remain owner-confirmed statements, not machine-enforced medical rules.

Confirmation status v1 is `unconfirmed|user_confirmed`; imported/derived describe provenance or analytical lifecycle, not confirmation enum values. Provenance origin and confirmation are independent: manual items saved explicitly are `user_confirmed`; future imported/derived values do not inherit that status. Keep `ai_use_allowed` and `cross_domain_use_allowed` permission fields in the canonical contract (default false); no AI behavior now. History/relationships inherit restrictive access. Source references must be owner-resolved and cannot be reassigned to another owner.

## Profile API and client/UI contract

All routes below are planned. Stable operation IDs; explicit request/response schemas; no generic JSON object-write API. `/healthz` stays public process liveness. Add:

- `GET /profile?as_of=<UTC>&category=...&limit=...&cursor=...` returns items plus next_cursor and as_of. Default limit 50, maximum 100; stable `(created_at,id)` ordering/cursor bound to owner/filter. Each DTO includes envelope, typed payload, source summary, confirmation and revision.
- `POST /profile` accepts client UUID `id`, Profile v1 content and validity/permission choices. Derive owner/source/actor/status/timestamps on server. Same owner ID plus identical canonical create content returns original object; reused ID with different content returns 409. Store a create-content fingerprint independent of later updates; retry must never revert edits. Return 201 first creation, 200 identical retry.
- `GET /profile/{id}`, `GET /profile/{id}/history` (bounded revision paging), `PATCH /profile/{id}` with `expected_revision`, and `DELETE /profile/{id}?expected_revision=...` as logical archive. Explicit null clears optional values; omitted PATCH fields preserve them. One transaction checks revision, validates content, updates envelope/subtype and appends history. Return 409 on stale revision and force refetch; do not silently merge conflicting edits. Archived objects remain accessible through explicit history/detail for their owner and absent from active listing.
- Relationships are a narrow application capability with tests in this phase; expose nested profile relationship create/remove/query only if needed by Profile details, documenting exact generated routes. No generic graph editor is required. Unsupported relations reject rather than inventing semantics.

Transport errors: 401 missing local principal configuration, 404 unknown or foreign object (no existence disclosure), 422 malformed/unknown schema/unit/invalid validity, 409 revision/ID conflict, sanitized 503 DB unavailable. A planned error handler returns stable `{code,message,field_errors?,request_id}` without submitted values/stack traces. Limit bodies/strings and document these bounds in OpenAPI. Use explicit authorization on list/detail/history/relationship joins. Connection/session lifecycle is request-bounded; choose simple synchronous SQLAlchemy 2 + psycopg for this small service, with short transactions and no async façade over synchronous IO.

Mobile app routes stay thin; planned `src/features/profile` owns screens/forms/query state and `tests/profile` owns tests. Profile overview grouped by category, detail with provenance/effective dates/history, create/edit, archive confirmation. Display unknown explicitly; every field optional except structural label/kind/type. Save disabled during submission; success refetches server truth. Loading/empty/retry/not-found/conflict states are recoverable. Failed request retains in-memory form data; no persisted health cache or offline write queue. Accessibility labels, focus/error announcements, font scaling and usable touch targets. Add only Profile navigation from the shell; further surfaces arrive with their phases.

## Execution graph and work packages

`P1.1 schema/principal -> P1.2 persistence -> P1.3 API/contracts -> P1.4 mobile -> P1.5 integration evidence`. Validation fixtures can be authored alongside schemas. Mobile visual forms can proceed against generated fixture DTOs after P1.3 contract agreement, never handwritten parallel DTOs.

### P1.1 — Freeze identity, payload and temporal rules

**Dependencies:** reconciliation. **Goal:** one contract before tables or forms.

**Areas/artifacts:** existing domain/config/integrations layer directories; provisional schemas, principal dependency and environment settings modules; `docs/data/data-model.md`, `docs/api/api-contract.md` clarifications.

**Work:** implement the v1 registry, enum/value/quantity/permission rules, UTC validity validation, local principal guard, immutable actor/source resolution and sanitized error model. Document accepted planning choices, object/history representation and reserved future kinds without implementing them.

**Invariants:** unknown/false/zero distinct; disabled non-local dev auth fails startup; owner never comes from submitted content; reject unsupported schema versions.

**Tests:** domain boundary/NaN/infinity/extra-field/length/unit cases; null vs omission; invalid windows; local/non-local auth settings. **Acceptance:** schema fixtures and docs agree, no DB or mobile hidden duplicate rules. **Out of scope:** real Firebase verification, AI policy execution, clinical ontology.

### P1.2 — Build migrations and owner-scoped repositories

**Dependencies:** P1.1. **Goal:** transactional durable Profile/history.

**Areas/artifacts:** existing root `migrations/`, persistence/application directories; provisional root `alembic.ini`, Alembic env/revisions and owner-scoped repositories; tests under `services/api/tests`.

**Work:** initialize Alembic at root using backend metadata; create only Phase 1 tables, constraints and indexes for owner/category/current/profile/history queries. Implement create/update/archive/relationship services and create fingerprints; central transaction boundary for subtype + history. Test against PostgreSQL 17, not SQLite JSON substitutes. Seed only a deterministic local principal, no realistic personal health data.

**Invariants:** failed validation/concurrent update leaves no partial rows/history; initial and subsequent revisions monotonically increase; cross-owner FK/edge fails. **Tests:** empty upgrade, downgrade/upgrade disposable DB, temporal querying, immutable revisions, repeated create after edit, concurrent stale PATCH, archive/history and FK ownership. **Acceptance:** persisted Profile survives restart and all failure cases are atomic. **Out of scope:** Phase 2+ subtype tables, migration-at-request/startup, cloud connections.

### P1.3 — Deliver narrow routes and generated contracts

**Dependencies:** P1.2. **Goal:** one authoritative transport contract.

**Areas/artifacts:** API/application layers and `main.py`; `contracts/openapi/`; `packages/api-client/package.json`; provisional OpenAPI export script and generated client directory.

**Work:** wire thin Profile routes, typed responses and bounded pagination/errors. Select and pin a minimal OpenAPI TS generator (types plus fetch client, no frontend framework), replace failing placeholder with real `generate`; export deterministic schema without DB/cloud calls. Decide tracked vs regenerated artifacts explicitly; prefer tracked schema/client with CI regeneration diff for reproducible reviews, remove generated ignore only for the chosen committed artifacts. Add package exports/build/typecheck only for actually consumed code. Document exact export/generation commands and stable operation IDs.

**Invariants:** backend owns DTOs; secrets/DB handles never in OpenAPI/mobile; every route owner-scoped. **Tests:** endpoint malformed/foreign/missing/conflict/DB-failure matrix; generated client compile and sample calls; deterministic regeneration in clean install. **Acceptance:** mobile can import a working `@personal-health/api-client`; CI checks drift. **Out of scope:** shared generic data sources, future web build, generic write tools.

### P1.4 — Complete the Profile vertical slice

**Dependencies:** P1.3. **Goal:** optional Profile management on mobile.

**Areas/artifacts:** existing app routes, `src`, `tests`; provisional Profile feature, API configuration/client instance and component tests.

**Work:** replace scaffold entry with access to Profile, use generated DTOs, one lightweight server-state boundary, configurable public API URL and private-local networking instructions. Establish Expo-compatible React Native component tests (e.g. Jest Expo + RN Testing Library pinned through current SDK); retain Vitest only if pure TS tests justify both runners. Scope tests to separated test directories and update real CI commands. Keep forms/accessibility local; create tokens package only if this slice needs reusable tokens.

**Invariants:** no silent zero defaults, no health console logging, no persistent cache of sensitive forms; retries respect IDs/revisions. **Tests:** empty/category/detail/loading/error/save/conflict/archive UX, null/false/zero entry, generated client integration; manual simulator create/edit/history walkthrough. **Acceptance:** Profile can be managed end to end locally; device networking documented. **Out of scope:** Add, Today, placeholder Assistant/Insights screens, web-ready component abstraction.

### P1.5 — Reconcile and hand off the foundation

**Dependencies:** P1.1–P1.4. **Goal:** Phase 2 receives tested truth.

**Areas/artifacts:** CI, local guide, model/API docs; provisional `docs/implementation/evidence/phase-1-release.md`.

**Work:** run clean bootstrap/migration/API/mobile scenario; review owner/source/permission/time contracts and clean generated diff; update actual paths/commands and Phase 2 assumptions.

**Tests:** all package checks plus migration/restart scenario and mobile launch; inspect logs for synthetic sensitive payloads. **Acceptance:** evidence captures actual revisions/routes/config/generator and remaining gates. **Out of scope:** product expansion to resolve unrelated roadmap wishes.

## Migration, rollback and verification matrix

Root Alembic history is authoritative; never create tables with `create_all` on service startup. Downgrade tests use disposable synthetic DBs; reverting initial production data would destroy health state and needs backup/export review. Future payload versions add migrations/converters with preserved original revisions. Archive is not privacy erasure; Phase 9 implements physical deletion.

| Risk                    | Deterministic/local verification                                       | External/manual gate                                      |
| ----------------------- | ---------------------------------------------------------------------- | --------------------------------------------------------- |
| Schema/time/unknown     | Unit fixtures with zero/false/null, boundaries and schema errors       | None                                                      |
| Ownership/history/races | PostgreSQL integration, two principals, concurrent writes and rollback | Docker equipped host                                      |
| Contract drift          | Export/generate/typecheck and clean diff in CI                         | None                                                      |
| Profile behavior        | Component and API integration tests                                    | Actual iOS render, keyboard and accessibility walkthrough |
| Bootstrap privacy       | Clean .env local run, fail-closed dev mode, sanitized logs             | No cloud identity claim                                   |

Commands: existing foundation checks in [local guide](../../local-development.md); planned `alembic upgrade head`, `alembic downgrade base` on disposable DB, real generated-client command and product test commands must be added/documented by P1.3–P1.5. Do not report future commands as already available.

## Phase acceptance, completion review and evidence

Accept when one local user can create/read/edit/archive Profile, revisions/provenance survive restart, duplicate creates/stale edits are safe, foreign users cannot query history/edges, migrations and generation are repeatable, and real mobile tests replace the empty-test assurance. No AI/cloud/native/web code.

Before Phase 2: Are all fields/permission defaults/temporal semantics explicit? Is ownership enforced below routes? Do sources/revisions stay consistent in failed writes? Is generated OpenAPI/client authoritative? Are local setup and actual mobile launch verified or clearly gated?

The implementing Luna Max session must create `docs/implementation/evidence/phase-1-release.md` with actual schema/table/index/migration head, payload examples (synthetic), routes/errors/idempotency/revision semantics, local principal/settings, generated artifact policy/commands, test/runtime results, mobile evidence, unresolved checks and accepted deviations. Include the schema registry extension procedure and Phase 2 consumption points. Do not fabricate this release evidence during planning.

## Implementation results (2026-10-03)

P1.1–P1.4 implementation is committed. The mobile app has a Profile-only entry point and real overview, create, detail, edit, archive-confirmation, and revision-history routes. It uses the tracked generated client, keeps failed form values in memory, preserves revisions for optimistic concurrency, refreshes from server truth on focus, and has no persistent health cache or offline write queue. Its form explicitly represents unknown, false, zero, quantity units, validity, notes, and disabled-by-default permissions. The accessible controls and touch targets are in place; the default iOS Metro bundle succeeds.

The mobile package retains Vitest and includes model/client tests plus a React DOM server-render smoke test with test-only native element stubs. This verifies the first render's accessible labels and permissions-off defaults, not native interactions, keyboard behavior, screen-reader flow, or visual layout. No compatible React Native component-rendering library was present in the available install, and local pnpm is version 11.19 while the repository pins 9.15.0; no network package install was available. CI runs strict app typecheck, lint, all seven Vitest tests, and an iOS Expo export. Actual simulator/device interaction and accessibility checks remain release gates.

The local Mobile API URL is `EXPO_PUBLIC_API_URL`; it contains only the address and is compiled into the bundle. iOS simulator defaults to `http://127.0.0.1:8000`, Android emulator uses `http://10.0.2.2:8000`, and physical-device use requires a secure private-network endpoint. Server credentials and the local principal remain server-only.
