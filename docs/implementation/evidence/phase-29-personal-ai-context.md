# Phase 29 evidence — Personal AI Health context

Date: 2026-10-11

Health base revision: `a0c170a7e39a88efae65ecbf4ebffdb07b7461a0`

Personal AI base revision: `158b569e7ad28c350f701b7e78d1fd38f2127b6d`

## Local implementation

Health exposes a separate `POST /v1/integrations/personal-ai/context` contract
(`health-context-read-v1`) behind `PERSONAL_AI_CONTEXT_READ_ENABLED=false`.
It is not `AIContextPack` and is not mounted unless the independent gate is
enabled. The live Assistant status/message contract and
`PERSONAL_AI_ENABLED=false` remain unchanged.

The route checks request and token bounds, verifies a Google service ID token
against the configured audience and exact service-account email, and verifies
a recent Firebase owner token with revocation checking before resolving the
existing exact `(issuer, subject)` mapping. It does not accept an owner ID,
create an owner, or map by email. The database transaction is read-only with a
short statement timeout on PostgreSQL.

The application projection reuses `_eligibility_conditions` and adds an
independent `cross_domain_use_allowed` condition. Both local AI-use permission
and cross-domain permission, owner, current/active state, and temporal
eligibility are checked before category discovery or row retrieval. The
contract exposes only categories implemented by the pinned Health revision:
profile background/constraints/preferences, measurements, nutrition,
exercise, sleep, and symptoms. It omits custom tracker observations and
medications because the current Health model does not provide those
capabilities.

Rows are typed and bounded; projection preserves object/source identity and
revision, source kind, confirmation, authority, observed/effective/expiry
times, units, selected quality fields, uncertainty, field-level sensitivity,
and permission dependencies. `verify` repeats the owner and eligibility
checks for the exact record before Personal AI reuse or dispatch. The route
has no mutation, proposal, or persistence operation.

## Architecture audit

- Health remains the only canonical owner of health records, consent,
  validation, and writes; no migration or duplicate state was added.
- Local preview/search keep their existing behavior because the shared
  eligibility predicate's cross-domain filter is opt-in.
- The transport is a dedicated typed projection, not a serialization of
  `AIContextPack` and not a Health adapter that imports Personal AI modules.
- Service identity and user identity are independently verified. There is no
  email mapping, owner auto-creation, body-supplied authority, or privilege
  escalation from local AI consent to cross-domain consent.
- No Health mutations or owner-authored proposal behavior changed. Future
  Phase 30 grants and Phase 31 proposals remain separate contracts.

## Verification

- API suite: 179 passed, 73 skipped, one Starlette/httpx deprecation warning.
  Database-backed cases skipped because `TEST_DATABASE_URL` was unavailable.
- Ruff passed for all changed API source and test files.
- Mypy passed for the 8 changed API source files.
- Contract and projection coverage includes gate-off behavior, separate
  credentials, revoked/stale identity rejection, owner resolution, category
  authorization, cross-domain denial, local-preview permission preservation,
  bounded profile/history, time, units, quality, unknown uncertainty,
  category/schema checks, and permission revalidation.
- `git diff --check` is recorded after final evidence edits.

These checks use local fakes and fixtures. They do not verify PostgreSQL,
Firebase/Google live identity and revocation behavior, Cloud Run/IAM, live
Personal AI calls, provider privacy, or real Health data.

## Open activation gates and deviation

The current Personal AI adapter has a verified Google OIDC user token; Health
requires a recent Firebase ID token. No delegated-token exchange or accepted
mapping is implemented. Health's cross-service read gate remains false, and
Personal AI's Health provider gate remains false. Daily records default
cross-domain consent off and there is no owner-facing grant control.

The Phase 29 sidecar category selector is intentionally not activated. It
cannot safely display only authorized categories without the authenticated
catalog path and a supported cross-domain consent control. Copy is the only
allowed action, and AI-originated Health proposals remain unavailable. The
OpenAPI export and generated client were not verified: the export could not
write its target under the restricted execution context, and the installed
pnpm 11.25.0 does not match the repository's supported `>=9 <10` range.

## Post-implementation review follow-up — 2026-10-11

The review follow-up adds a revisioned owner path for daily cross-domain
consent. Daily Event and Observation create/update requests now accept
`cross_domain_use_allowed`; updates use the existing expected-revision lock,
advance `HealthObject.revision`, and append the consent snapshot to ordinary
revision history. Health context permission versions include the current object
revision and both source-consent flags. The database regression case exercises
revoke, denial, regrant, and dependency-version change through the Health
service. This case was collected but skipped locally because
`TEST_DATABASE_URL` is unavailable; no PostgreSQL result is claimed.

The Personal AI shared `ContextItem` now carries generic partial-result
metadata into the model-visible source envelope. Truncated Health responses
remain usable with `partial_result=true`. Health capabilities are unavailable
in the Personal AI registry while the delegated identity contract is
incompatible, and their feature flag cannot activate them. Health source
consent remains distinct from the future Phase 30 federation grant: effective
access must require both, and their dependency versions remain separate.

Verification on the 2026-10-11 worktree based on Health `1c1f442` and Personal
AI `cdab864`:

- Health focused API/contract run: **7 passed, 16 skipped**; skipped tests
  require `TEST_DATABASE_URL`.
- Health Ruff: passed on all changed Python source and test files.
- Health Mypy: passed on the four changed API source modules.
- Health OpenAPI JSON and generated TypeScript client were regenerated with the
  repository scripts; API client TypeScript typecheck passed. The documented
  pnpm wrapper could not run because installed pnpm is 11.25.0 while the
  repository requires pnpm 9.x; the underlying generator commands succeeded
  using the bundled Node runtime and service virtualenv.
- Personal AI focused Health/Shopping tests: **17 passed**; the final full
  backend suite then passed with **1,398 passed, 82 skipped**. Generic
  partial-result serialization is covered by these checks.
- `git diff --check` passed after the evidence update.

Live Firebase/Google verification, PostgreSQL, Cloud Run/IAM, live Personal AI
requests, provider privacy review, and the category sidecar remain open. The
Health provider is deliberately unavailable until a Health-verifiable delegated
user authority is accepted and implemented.

## Owner-facing daily consent UI follow-up — 2026-10-11

The mobile daily-entry form now exposes the default-off
`cross_domain_use_allowed` control for creating and editing Event and
Observation records. The choice is submitted with the existing revision-checked
update, so Health's canonical revision history and permission epoch remain the
source of truth. Linked symptom-severity observations receive the same explicit
consent as their Event. This source-domain permission does not enable the
disabled Personal AI integration.

Verification after the UI change:

- Daily model and form rendering tests: **22 passed**.
- Mobile TypeScript typecheck: passed.
- Prettier check on all changed mobile files: passed.
- Full Health API suite: **179 passed, 75 skipped**; skipped database checks
  require `TEST_DATABASE_URL`.
- OpenAPI export matched the committed, Prettier-formatted artifact.
- Ruff and Mypy passed for the changed API source and test files.

The database-backed revoke/regrant check, live identity, deployment, provider
privacy, and sidecar checks remain unverified.
