# Personal AI boundary alignment evidence

**Checkpoint:** October 8, 2026. This handoff removed Health's stale disabled
message transport seam and aligned current Health documentation with the
Personal AI Application Integration Contract direction. It did not enable
Personal AI traffic or implement Health Phase 29.

## Reconciled baseline

- Health HEAD was `75ff343fa37f188b91ad3d62eaaf91607f47a38c`, matching the
  handoff's reviewed baseline. The shared working tree already contained
  uncommitted Phase 9 work; that work was preserved.
- Personal AI HEAD was
  `2b30bc99888f91892ec7d7dbe153590c22b44d52`, later than the handoff's
  reference SHA. Its current code and architecture docs show registered typed
  providers, bounded operations, permission dependencies, field sensitivity,
  deterministic planning before retrieval, and a shared context builder.
  Phase 29 Health providers and Phase 31 domain mutation capabilities remain
  planned there.

## Implemented in Health

- Removed `PersonalAIAdapter.send_message(request, context)`, its static
  `READ_CAPABILITIES`, timeout/response-validation machinery, and the app's
  adapter injection hook. The factory now returns only disabled integration
  status and a reason.
- Kept `/assistant/status` authenticated and owner-scoped, reporting disabled
  with an empty capability list. Kept `/assistant/messages` and its request
  schema for client compatibility; it now returns sanitized 503 without
  building Health context or calling an adapter.
- Kept `PERSONAL_AI_ENABLED=false` and rejected `true` in settings validation.
  `/ai/context` and `/search` remain local Health features.
- Documented `AIContextPack` as a local preview model, not the future
  cross-service envelope, and updated the Health integration, API, and current
  state docs. OpenAPI descriptions were regenerated; generated TypeScript
  remained unchanged.
- No `personal-ai-system` files changed.

## Validation

- `python scripts/verify_scaffold.py` — passed.
- `pytest -c services/api/pyproject.toml services/api/tests` — 161 passed,
  62 skipped. The PostgreSQL integration cases were skipped because
  `TEST_DATABASE_URL` was not set. Database-free API route tests use synthetic
  preview/search service results to confirm `/ai/context` and `/search` remain
  available without Personal AI; they do not establish database behavior.
- Ruff check on changed production and test files — passed. The repository-wide
  Ruff command still reports 30 import-order findings in untouched files.
- Ruff format check across API source, tests, and scripts — passed.
- Mypy on the changed production boundary modules — passed (5 files). The
  requested repository-wide command hit a mypy internal error in
  `typeshed/stdlib/zipimport.pyi`; a package-only run also reports existing
  diagnostics in the broader migration, account-data, analytics, and AI-context
  source paths, none in the five boundary modules checked separately.
- OpenAPI export and API-client generation were run directly through the
  repository Python environment and bundled Node runtime because installed
  pnpm is 11.25.0 while the repository requires pnpm 9.15.0. Repeating
  generation produced identical hashes. API-client TypeScript check passed.
- Mobile TypeScript check passed. Mobile lint exited successfully with six
  warnings in existing test files. Mobile tests passed (125 tests across 25
  files).
- Prettier passed for the updated integration, API, current-state, and
  Personal AI docs. Repository-wide Prettier still flags the untouched
  `phase-7-independent-review-handoff.md`; the `pnpm format:check` wrapper
  could not run under pnpm 11 due the declared engine range.
- Local Markdown links in the five updated documentation files and the Git
  whitespace check passed.

## Remaining gates

The shared external contract, delegated owner authorization, Health provider
registration, retention/privacy review, live read-only safety evaluation, and
provider behavior remain unverified. Live messaging remains disabled, and
canonical health state remains owned by Health.
