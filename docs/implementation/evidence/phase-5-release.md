# Phase 5 release evidence

**Checkpoint:** October 5, 2026. Local Health-side context, search, consent,
and Assistant preview are implemented. The Personal AI provider adapter is
disabled because no external service/auth/delegation/tool/retention contract
was supplied. This is not a live AI integration or safety acceptance.

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
  PostgreSQL `simple` full-text query parsing and returns a bounded plain-text
  excerpt; its cursor binds to owner, query, and type filters.
- Additive migration `f5c0a1e2d3b4` adds five GIN full-text indexes over
  envelope title/notes and typed Profile/Event/Observation/planning payloads.
- Daily Event/Observation create and edit flows now expose an item-level AI
  permission, default off. Permission changes use normal optimistic revisions
  and appear in daily history snapshots. Compound creates apply the flag to
  each submitted object. Legacy permission-off uncertain-create retries retain
  their prior fingerprint behavior.
- `PERSONAL_AI_ENABLED` defaults off and rejects `true` until the real contract
  is configured. The adapter factory returns only `DisabledPersonalAIAdapter`;
  no provider URL or credential path exists. `GET /assistant/status` is
  authenticated. `POST /assistant/messages` checks adapter availability before
  constructing context and returns sanitized 503 while disabled. If a future
  adapter is injected, Health rebuilds context at send time, enforces the
  requested risk floor, and rejects evidence refs that do not match included
  object revisions.
- Mobile adds Assistant navigation, selected resource-type scope, local
  context preview, included source/revision details, current-day summary,
  permission-filtered search, an in-memory message draft, and a disabled send
  state with the reason shown. Profile/Plan/daily entry screens remain the
  locations where item-level permission is edited. Session remount clears the
  Assistant screen state.

No proposals, saves, history reads, tracker definitions, trends, records,
arbitrary relationship expansion, delegated callbacks, provider registration,
or cross-domain sharing were added.

## Contracts and configuration

- `POST /ai/context`: task (1–300 chars), task kind, selected resource types,
  lookback (0–90 days), optional aware `as_of`/IANA timezone, and optional
  excluded object IDs.
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
- `.venv/bin/alembic heads` reports one head: `f5c0a1e2d3b4`. Offline
  `alembic upgrade head --sql` generated the complete migration chain and all
  five index statements. No PostgreSQL database was available for applying the
  migration, downgrade/re-upgrade, drift check, or query-plan measurements.
- `git diff --check` — passed.
- No test files were added and no tests were run in this implementation turn.

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
- Apply migration `f5c0a1e2d3b4` to a disposable PostgreSQL database, test its
  lifecycle/model drift, and measure full-text query plans/cost.
- Run the app on an equipped device for VoiceOver, keyboard, session-switch,
  scope readability, timezone, and disabled/unavailable state review.
- Carried forward from prior phases: PostgreSQL acceptance, live cloud
  auth/storage parity, and device release gates remain open as recorded in
  Phase 4 evidence.
