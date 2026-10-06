# Phase 5 release evidence

**Checkpoint:** October 5, 2026. Local Health-side context, search, consent,
and Assistant preview are implemented. The Personal AI provider adapter is
disabled because no external service/auth/delegation/tool/retention contract
was supplied. This is not a live AI integration or safety acceptance.

**Independent review follow-up:** planning payload dates now participate in
context and search eligibility; Today symptom summaries use only included
event/observation links; search excludes relationship fields from both FTS
matching and excerpts; and per-request domain/item narrowing is available.
Mobile preview/search results become stale on focus/filter changes. Daily form
render tests cover the consent Switch. Custom tracker entries expose a
permission-only edit while remaining excluded from AI context until their
immutable field schema can be safely interpreted. The injected adapter path
has a 30-second Health deadline, request correlation, evidence validation, and
Health-derived context counts. The real adapter remains disabled.

## Reconciliation and scope

The repo contains no Personal AI service or supplied API contract. Phase 3
provides verified Firebase end-user identity, but no separate service identity
or delegated user capability. Existing Profile and planning resources had
`ai_use_allowed` fields and UI; daily Events/Observations were permanently
off. The existing canonical model has source kind and confirmation status but
no confidence score, so Pack entries use only fields that actually exist.

Implemented locally:

- Versioned Health-owned `AIContextRequest`, `AIContextPack`, search and
  Assistant DTOs under `health_api.domain.ai`.
- `POST /ai/context` and `GET /search`, both owner-scoped and restricted to
  active, valid, selected resources with `ai_use_allowed=true`. Context daily
  history uses the requested local-day window, bounded to 90 days. Search
  daily resources are bounded to 90 days and pages to 50 items. Requests use
  a two-second PostgreSQL statement timeout.
- Context ranking places Profile constraints first, then active contexts
  (using their explicit priority), goals/preferences/plans, Profile facts, and
  recent daily entries. Confirmed items rank before unconfirmed items within
  each class; source kind is included as provenance but receives no invented
  confidence score. It includes at most 100 entries / 65,536 serialized
  bytes. It marks truncation and fails with 422 if an eligible Profile
  constraint cannot fit. Today summaries reuse `summarize_today` over only the
  included, opted-in entries; the response labels that coverage scope.
- Cross-object plan/context references remain only if the target also appears
  in the same Pack. Notes and payload text are labeled user data. Search uses
  PostgreSQL `simple` full-text query parsing over title/notes and a JSON
  projection with relationship fields removed. Its cursor binds to owner,
  query, and type filters.
- Additive migration `f5c0a1e2d3b4` adds five GIN full-text indexes.
  Migration `6a0b1c2d3e4f` replaces payload indexes with the relationship-safe
  search projection.
- Daily Event/Observation create and edit flows now expose an item-level AI
  permission, default off. Permission changes use normal optimistic revisions
  and appear in daily history snapshots. Compound creates apply the flag to
  each submitted object. Legacy permission-off uncertain-create retries retain
  their prior fingerprint behavior.
- Daily custom tracker records can change only their AI permission. Their
  values are excluded from context and search because the current Pack cannot
  join immutable field labels, value types, and units within the authorized
  tracker-definition boundary.
- Context scope accepts bounded domain and section narrowing and item IDs to
  exclude for one request. Exclusions are counted only when they resolve to an
  otherwise eligible owner row. Budget omission counts include rows beyond the
  1,000-row retrieval cap.
- `PERSONAL_AI_ENABLED` defaults off and rejects `true` until the real contract
  is configured. The adapter factory returns only `DisabledPersonalAIAdapter`;
  no provider URL or credential path exists. `GET /assistant/status` is
  authenticated. `POST /assistant/messages` checks adapter availability before
  constructing context and returns sanitized 503 while disabled. If a future
  adapter is injected, Health rebuilds context at send time, enforces a
  30-second deadline and request correlation, derives inclusion counts from
  its own Pack, enforces the requested risk floor, and rejects evidence refs
  that do not match included object revisions.
- Mobile adds Assistant navigation, selected resource-type and domain scope, local
  context preview, included source/revision details, current-day summary,
  permission-filtered search, an in-memory message draft, and a disabled send
  state with the reason shown. Profile/Plan/daily entry screens remain the
  locations where item-level permission is edited. Users can exclude a listed
  item for the current request. Focus changes invalidate previews and search
  results; filter changes reset paging and discard older requests. Session
  remount clears the Assistant screen state.

Phase 4 schedule occurrences, effective schedule versions, and completion,
skip, or reschedule state are **deferred from the Phase 5 Pack**. The Pack
therefore provides current planning resources and actual-log summaries, not a
complete Today intent view. A follow-up must add bounded scheduled intent with
parent/target permission checks and keep intent separate from actual records
before the product can claim complete Today/planning context.

No proposals, saves, history reads, tracker definitions, trends, records,
arbitrary relationship expansion, delegated callbacks, provider registration,
or cross-domain sharing were added.

## Contracts and configuration

- `POST /ai/context`: task (1–300 chars), task kind, selected resource types,
  lookback (0–90 days), optional aware `as_of`/IANA timezone, and optional
  excluded object IDs, domains, and response sections.
- `GET /search`: `q` (1–500 chars), optional comma-separated `types`,
  `limit` (default 20, maximum 50), and owner/query/filter-bound cursor.
- `POST /assistant/messages`: message (1–8,000 chars) plus the context scope;
  current status is disabled.
- `GET /assistant/status`: reports `disabled` with no active capabilities.
- Server-only flag: `PERSONAL_AI_ENABLED=false`. Setting it true fails settings
  validation. The removed `.env.example` `PERSONAL_AI_BASE_URL` was a
  placeholder and was not retained as a configurable endpoint.
- OpenAPI and generated client include the new routes and schemas. Generation
  now formats the client with the workspace Prettier dependency.

## Local static verification

- `.venv/bin/ruff check` on changed API, config, model, and migration files —
  passed.
- A broader Ruff check found six import-order issues in unchanged API files
  (`dependencies.py`, `profile.py`, `envelope_service.py`,
  `local_principal.py`, `profile_service.py`, and `provider_identity.py`); the
  changed-file check above is clean.
- `.venv/bin/mypy services/api/src/health_api` — passed, 32 source files.
- Mobile `tsc --noEmit -p apps/mobile/tsconfig.json` — passed.
- ESLint on changed mobile files — passed.
- Prettier check on changed mobile, client, and documentation files — passed.
- FastAPI OpenAPI export — passed. The standard `pnpm` command could not run
  because the host provides pnpm 11.19 while this repo requires pnpm 9; its
  attempted `pnpm dlx pnpm@9.15.0` was blocked from creating a host cache
  directory. The repository generator itself was run directly with the
  bundled Node runtime and pinned workspace Prettier; generated artifacts are
  committed.
- `.venv/bin/alembic heads` reports one head: `6a0b1c2d3e4f`. Offline
  `alembic upgrade head --sql` generated the complete migration chain. No
  PostgreSQL database was available for applying the
  migration, downgrade/re-upgrade, drift check, or query-plan measurements.
- `git diff --check` — passed.
- API suite — 122 passed, 48 skipped. The skipped PostgreSQL integration tests
  require `TEST_DATABASE_URL`; new database-free review tests cover cursor
  shapes/binding, request narrowing, planning date SQL, relationship-safe FTS
  projection, adapter timeout, response binding/evidence/count validation. Two
  PostgreSQL context/search permission and linked-severity tests are included
  but skipped without the disposable database.
- Mobile full suite — 95 passed across 20 files. The daily form render suite
  now passes all 8 cases. TypeScript and mypy passed.
- ESLint on changed mobile files — passed when invoked from `apps/mobile`.
- The standard `pnpm` command could not run because the host provides pnpm
  11.19 while this repo requires pnpm 9. OpenAPI export and client generation
  were run directly through the installed Python and Node runtimes.
- `git diff --check` — passed.

## Open gates

- Supply and review the real Personal AI endpoint, service identity, end-user
  delegation, tool registration/callback, retry/timeout, and retention
  contracts before implementing or enabling a live adapter. The current
  message endpoint is intentionally unavailable.
- Review the actual provider's logging/retention and run synthetic live
  read-only authorization, owner-isolation, evidence, timeout, and malformed
  response checks. Mocks and the disabled adapter cannot certify provider
  behavior.
- Approve authoritative safety policy/copy and evaluate the real provider's
  response behavior for consequential and urgent-safety requests. No clinical
  validation is claimed.
- Apply migrations through `6a0b1c2d3e4f` to a disposable PostgreSQL database, test its
  lifecycle/model drift, and measure full-text query plans/cost.
- Run the app on an equipped device for VoiceOver, keyboard, session-switch,
  scope readability, timezone, and disabled/unavailable state review.
- Carried forward from prior phases: PostgreSQL acceptance, live cloud
  auth/storage parity, and device release gates remain open as recorded in
  Phase 4 evidence.
