# Phase 3 — Cloud baseline with local equivalence

## Implementation-time reconciliation gate

**Status: planned. Dependencies: accepted Phases 1–2 and their actual release evidence.** Read [Phase 3 roadmap](../implementation-plan.md#phase-3--cloud-baseline), ADR 0002, security/deployment docs, actual principal/auth settings, migrations, daily/Profile routes and generated mobile client. Inspect local bootstrapping and locks before selecting images/config. Record drift and update plan/ADR before a material change.

Real Phase 0 paths: `infra/gcp/README.md`, `infra/docker/README.md`, root `docker-compose.yml`/`.env.example`, API layered source/tests, mobile source/tests and `.github/workflows/ci.yml`. Auth, storage adapters, container/IaC/cloud resources below are **planned/provisional**. Preceding product code is assumed accepted at execution time, not already present now.

## Outcome and strict boundary

**Deliver:** deploy existing Profile/daily capabilities through Cloud Run to isolated Neon, Firebase-compatible shared identity, and private GCS storage wiring while preserving local PostgreSQL/dev identity/local-object development. A signed-in user accesses only their own existing objects from mobile.

**Defer:** records/upload/extraction/product signed-URL routes to Phase 9; Personal AI/service delegation to Phase 5; planning/HealthKit/web; speculative queues/cache/vector services. Storage wiring is tested with synthetic objects through adapter tests, not a new document screen/API.

## External decisions and verification gates

Before provisioning, identify the actual ecosystem Firebase project/issuer/audience and subject mapping, deployment project/region, Neon branch/region and supported SSL/pooling endpoints, private GCS bucket/retention policy, budget owner, and Secret Manager naming. These are required user/environment inputs when unavailable; progress with local tests and reviewable IaC while waiting. Existing authorization to implement this phase does not justify silently selecting someone else's cloud project or incurring unspecified spend. Record deployment approval where needed by repository/session policy.

Verify current official Firebase token verification/revocation, Neon connection/transaction pooling and plan limits, Cloud Run connection concurrency/request limits/region/pricing and GCS IAM/lifecycle behavior **at execution time**. Do not embed today's vendor terms as permanent facts. Mocks certify adapter logic only. Use accepted vendors; replacing them is a material ADR change.

## Identity and environment contract

`APP_ENV=local|test|cloud`; `AUTH_MODE=dev|firebase`; strict settings reject dev auth outside local/test and missing cloud essentials at startup. Database/object-storage/identity configuration must be congruent; do not infer local auth from missing token. Local dev principal is server-defined; Firebase principal comes exclusively from verified bearer token. Verify signature, issuer, audience, expiry and expected project; external verification library must have bounded key-fetch timeout/cache behavior. Invalid/expired token 401; authenticated foreign resource 404; actual verifier outage sanitized 503, no dev fallback. Enforce every owner-scoped repository/query/history/relationship/evidence path. Accept neither submitted owner IDs nor service credentials as user identity.

Map verified `(issuer, subject)` uniquely to a stable internal user UUID in one transaction. Repeated/concurrent first login produces one principal; do not merge users by email or reassign existing local data. Existing development user migration to cloud identity requires an explicit owner-verified mapping procedure, preferably fresh synthetic cloud accounts for first deployment. Principal settings/timezone remain domain-owned. Mobile obtains Firebase user token via a documented SDK/session boundary; tokens stay in appropriate platform storage, never logs/URLs. Auth expired state pauses requests and asks for sign-in; sign-out discards owner-scoped cached data. Guard against user switch showing previous cached profile.

Health API is public HTTPS ingress only where bearer-auth app access requires it; liveness may be public, domain endpoints always verify identity. CORS, if needed for future explicit callers, allow exact origins; native mobile alone does not need permissive CORS. Do not expose debug stacks or interactive API docs with real credentials/payloads; choose explicit cloud docs policy and document it. Routine logs contain request ID, route template, status, duration and operational counts, never tokens, object notes, request bodies, SQL parameter values or raw error response health values.

## Portable persistence/storage/deployment contracts

One DATABASE_URL per environment; Neon uses required verified TLS. Do not simultaneously use ambiguous DATABASE_URL/NEON_DATABASE_URL precedence; resolve to DATABASE_URL and document or remove the redundant example setting. SQLAlchemy sessions/transactions stay short; cap pool size and overflow according to max Cloud Run instances × workers × per-process pool. Start conservatively (one worker, pool5/overflow0, max2 instances, low concurrency) as provisional tunable bounds; reconcile with vendor limits/load evidence. Migrations run as a separate controlled release step with a suitable direct DB endpoint and least-privilege migrator, not app startup and not every container replica. Use backward-compatible migrations before rolling service revisions. `/healthz` remains dependency-free; a planned operational readiness check may test DB with short timeout and return no secret information, without confusing transient DB failure with process death.

Planned `integrations/object_storage` interface: put/get/delete opaque owner-namespaced key with size/content metadata and bounded streaming; local adapter roots paths safely under configured `.data/objects`, denies path traversal/symlink escape; GCS adapter uses workload identity/default credentials and private buckets. GCS signed access mechanism can remain reserved until Phase 9 product flow; test synthetic authorized object access and no public ACL. No client GCS/DB administrative credentials. Document content/object persistence independent of ephemeral Cloud Run filesystem.

API image in planned `infra/docker/api.Dockerfile`: supported pinned Python runtime, locked runtime dependency install, non-root user, no .env/test fixtures/objects/secrets in build context, container listens on injected PORT/0.0.0.0, bounded workers and graceful termination. Separate production dependency lock if dev constraints are unsuitable; retain tested compatibility. Planned minimal reproducible IaC/deploy scripts in `infra/gcp`, separate staging/live state, least-privilege runtime service account, Secret Manager references, private GCS, Cloud Run limits. No public DB port, blanket editor/admin permissions or checked-in key files. GitHub CI uses federated identity if deployment is authorized; build/test alone must need no credentials. Initial manual deployment is acceptable if repeatable and documented.

## Execution packages and release gates

`P3.1 environment/identity decisions -> P3.2 auth & parity -> P3.3 storage/container -> P3.4 provision/migrate/deploy -> P3.5 live isolation/rollback`. P3.3 can proceed after P3.1 alongside auth work; live deployment waits for both, tested owner isolation and identified credentials/budget.

### P3.1 — Lock configuration and cloud release inputs

**Dependencies:** reconciliation and supplied external identity/project details. **Goal:** fail-closed portable settings and reviewable release plan.

**Areas/artifacts:** config layer, `.env.example`, deployment/security/local docs; provisional environment matrix, secret-name-only config and budget estimates.

**Work:** validate settings combinations, document URLs/identity mapping/pool budget and required vendor verification; split secret values from public mobile config; establish synthetic staging accounts.

**Requirements:** no secrets in output/repository, no undocumented cloud defaults. **Tests:** startup matrix, missing/cloud-dev settings rejected, secret redaction, local boot no cloud access. **Acceptance:** explicit inputs and configuration contract; unavailable external inputs are recorded blockers for live work. **Out of scope:** replacing vendors, real data migration by guessing ownership.

### P3.2 — Implement verified auth and mobile session lifecycle

**Dependencies:** P3.1. **Goal:** user isolation across local/cloud modes.

**Areas:** integrations/api/principal repositories; mobile auth/client boundary; API/mobile tests.

**Work:** verified token adapter, unique provider-subject mapping, replace dev dependency by config-selected resolver; test all current routes/history/links; mobile sign-in/sign-out/token refresh and cache clearing.

**Requirements:** no token→owner shortcut, no fallback, no email-based merging. **Tests:** bad issuer/audience/signature/expiry, JWKS unavailable, cross-owner CRUD/query/history, first-login race, switch user/expired session. **Acceptance:** deterministic tests cover auth matrix; two real Firebase principals must be tested in P3.5. **Out of scope:** AI service principals, social-provider breadth not required by chosen identity.

### P3.3 — Wire portable storage and production container

**Dependencies:** P3.1. **Goal:** deployable existing service with safe object backend.

**Areas:** existing infra placeholders; provisional Dockerfile/dockerignore, storage adapter/tests.

**Work:** local/GCS adapters, bounded object IO with synthetic test-only usage, container locked install/PORT/non-root/termination and health endpoint. Keep product object routes absent.

**Requirements:** private keys/objects, path containment, ephemeral files not durable state. **Tests:** local path traversal/symlink escape, adapter error/size/timeout cleanup, image scan/build/run with synthetic local DB, no dev deps/secrets in image. **Acceptance:** container serves existing API and storage contract is portable. **Out of scope:** record upload/view UI, OCR/labs.

### P3.4 — Provision and release existing capabilities

**Dependencies:** P3.2/P3.3; live credentials/approval/budget gates. **Goal:** repeatable staging deployment.

**Areas:** provisional `infra/gcp` IaC/deploy scripts and runbook, migration release command; docs.

**Work:** minimal Neon/Cloud Run/GCS/secret/identity wiring; TLS, IAM, limits, migration lock/release ordering; deploy immutable image and explicit mobile public API URL/auth project. Inspect plan before apply under applicable authorization.

**Requirements:** independent environments, no migration inside serving process, preserve local parity. **Tests:** IaC/static validation offline; real migration/login/CRUD/readiness/storage round trip in staging; no public bucket/unauthenticated domain access. **Acceptance:** actual revision/migration/config inventory recorded. **Out of scope:** queues/jobs without long work, domain changes.

### P3.5 — Prove isolation, rollback and cost bounds

**Dependencies:** staging from P3.4. **Goal:** cloud evidence supports Phase 4.

**Areas:** integration tests/runbook; provisional phase-3 release evidence.

**Work:** replay Phase 1–2 synthetic scenario locally/cloud, two real identities, token expiry, DB/storage outage, process restart; service revision rollback and separate migration compatibility demonstration; observe connections/billing/log redaction.

**Requirements:** live checks labeled independently from mocks; don't put health fixtures in routine logs. **Tests:** unauthorized object access, shutdown/retry and pool saturation, revoked/expired token policy, restore/rollback on disposable staging. **Acceptance:** functional local/cloud parity and bounded resources; failed live gates reported honestly. **Out of scope:** disaster recovery guarantees or Phase 9 full backup/export workflow.

## Compatibility / safe failure / verification matrix

Auth is transport enforcement around existing domain ownership; never rewrite owner IDs wholesale. Add provider identity mapping via additive migration, preserved history. New deployment must tolerate rolling old/new image revisions against migrated DB; if schema needs breaking changes, stage expand/migrate/contract across releases. Roll back image first only when DB contract compatible; do not downgrade live health data without tested backup. API tokens/config changes require mobile/session coordination but no duplicate DTOs. Local dev mode remains available independently of Firebase network.

| Risk                    | Deterministic CI                                            | Required real gate                                            |
| ----------------------- | ----------------------------------------------------------- | ------------------------------------------------------------- |
| Settings/auth/isolation | Fake signed token fixtures + owner matrix                   | Two real Firebase users, key rotation/revocation policy       |
| DB portability/pools    | PostgreSQL tests, URL/TLS settings, bounded pool assertions | Neon TLS/pooling/migration, concurrency and connection counts |
| Storage/IAM             | Local containment and fake adapter failure tests            | GCS private access/runtime identity, no public ACL            |
| Runtime/security        | Image checks, no secret inclusion, local container          | Cloud Run PORT/restart/HTTPS/logs/timeouts                    |
| Release safety/cost     | IaC plan/rollback script validation                         | Staging rollout/rollback, current vendor terms/budget         |

## Acceptance and completion review

Existing Profile/daily behavior works locally and on a real authenticated staging deployment; owner isolation and state survive restart; storage private; migration/release repeatable; limits/secrets/logging reviewed. Ordinary local development still requires no cloud. No records/AI/planning/HealthKit/web added.

Before Phase 4: Can every domain request resolve one verified owner? Do missing external services fail closed? Is the pool budget within real limits? Does rollback preserve data? Are live auth/storage checks actually performed and remaining vendor decisions visible?

Luna Max must leave planned `docs/implementation/evidence/phase-3-release.md`: actual project/region identifiers (non-secret), deployed image/revision, IaC state procedure, migration head/run order, identity mapping and dev-mode restrictions, config/secret names, generated API procedure, local/cloud test results separately, IAM/storage/connection/budget evidence, rollback steps and unresolved gates. Link the cloud runbook without secret values; preserve costs as dated observations.
