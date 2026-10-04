# Phase 3 independent review

Main-session review through `e3ddd50`, October 4, 2026. Read the phase plan,
release evidence, configuration, identity mapping, Firebase verifier, HTTP
dependencies, mobile sessions/transport/routing, storage adapters, container,
Terraform, build/runbook and tests. Local implementation is reviewable; live
release remains gated. Phase 2's database checks are deferred by user instruction,
not passed. Fix agents spawned after the 15:05 PDT restart use Sol Medium.

## Required fixes

1. **P1: SecureStore persistence keys are incompatible with Firebase.**
   `firebaseSession.ts` passes Firebase keys directly into SecureStore. The
   installed Firebase RN SDK creates `firebase:authUser:API_KEY:[DEFAULT]`,
   while installed SecureStore permits only alphanumeric, dot, dash, underscore.
   Its availability probe can succeed while user persistence fails. Map keys
   deterministically and without collisions to legal names and test real
   Firebase-shaped keys against the SecureStore constraint. Cover SDK-backed
   persistence/restore/remove with a fake native store, not only SessionStore.

2. **P1: delayed rejected-session cleanup can sign out a new account.**
   `mobileFetch` marks the old epoch expired then asynchronously imports Firebase
   and calls unconditional `clearRejectedFirebaseSession`. An account can change
   before cleanup runs. Bind cleanup to the rejected epoch and UID and check
   before mutating SDK/session state. Cover old rejection, new account sign-in,
   then delayed cleanup, plus concurrent rejected requests. Avoid resurrecting
   expired users through auth callbacks and suppress stale callbacks/operations.

3. **P2: token acquisition failure never expires an invalid SDK session.**
   `getIdToken(true)` commonly rejects for revoked/disabled/invalid refresh
   tokens instead of returning a second HTTP 401. `authenticatedFetch` handles
   only the latter, leaving signed-in screens and repeated failing requests.
   Classify definitive auth errors versus transient network errors; expire and
   clear only the current definitively invalid session. Keep transient failures
   recoverable without destroying a good session. Add asynchronous regressions.

4. **P2: owner guard ends at headers, before the response body is consumed.**
   `authenticatedFetch` checks epoch after fetch resolves, then generated client
   awaits `response.json()` without a guard. An account switch during body
   parsing can let old-owner results finish after new-owner cache clearing.
   Guard through payload consumption and account for the generated client's
   blanket JSON catch, which must not swallow session-change failures. Test an
   actual client request with deferred JSON and a switch after headers. Keep
   generated code reproducible by changing its generator if needed.

5. **P2: Firebase builds silently accept missing/insecure API configuration.**
   Mobile auth mode defaults to dev for every value except exactly `firebase`;
   both API clients default to localhost HTTP even in Firebase mode and accept
   arbitrary HTTP endpoints for bearer tokens. Fail closed for invalid mode and
   require an explicit HTTPS API URL for Firebase builds. Preserve the explicit
   local dev flow. Test missing/malformed/insecure config and ensure no token is
   transmitted under invalid configuration.

6. **P2: cloud request logs violate the planned privacy contract.**
   The container starts Uvicorn with default access logging, recording raw paths
   and query strings (object IDs, cursor contents, time filters). There is no
   operational request log containing only request ID, route template, status
   and duration as required by the plan. Disable unsafe access logs and add a
   small redacted logging boundary; verify sentinels in headers/body/query/path
   values and SQL error details never appear. Include rejected/unmatched routes
   and exceptions without logging stacks or sensitive error representations.

7. **P2: migration Job does not serialize releases.**
   `task_count=1`/`parallelism=1` only serialize tasks within one execution;
   simultaneous Job executions can run Alembic against the same database.
   Implement a bounded PostgreSQL advisory release lock (or equivalent concrete
   guard), acquired before schema mutation and reliably released on errors,
   with sanitized contention failure. Add concurrency/cleanup tests, retaining
   DB-gated tests honestly if PostgreSQL remains unavailable. Do not run
   migrations during serving startup or downgrade live data.

## Verification and remaining acceptance

Add real SDK cryptographic token tests with local signed fixtures and controlled
certificate/revocation responses: current verifier tests mock verification
itself and do not exercise signature/expiry enforcement. Add authenticated
two-subject route/owner isolation tests through the new resolver; existing
dependency-wiring assertions are useful but cannot establish identity mapping
plus CRUD/history isolation. These integration tests may stay explicitly
PostgreSQL-gated, never replaced by SQLite as acceptance evidence.

Complete all independent fixes/checks in logical commits, update release evidence
and coordinator state and leave a clean tree. Validate Terraform offline and
generate/review its provider lock if a safely acquired local tool is possible;
do not treat an absent preinstalled executable as a definitive blocker. No
cloud provisioning, builds with spend, arbitrary identities or secret output.
Root will lightly re-review and verify. Live release inputs and the carried
database acceptance remain explicit human/environment gates before closing
Phase 3 or starting Phase 4.

## Fix disposition — October 4, 2026, after 15:05 PDT

The review baseline is `8b6c093`. All seven code premises were confirmed.
Earlier uncommitted edits were preserved and completed. Root's independent
re-review is the next step; these dispositions record implementation and local
verification, not live acceptance.

| Finding | Implemented disposition and regression evidence                                                                                                                                                                                                                                                                                                                                                                                           |
| ------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1       | `4d2dd7a`: injective fixed-width UTF-16 key encoding produces legal SecureStore keys. The installed `@firebase/auth` 1.13.6 RN persistence class probes, writes, restores and removes through a fake constraint-enforcing native store, with distinct Firebase-shaped/collision-candidate keys.                                                                                                                                           |
| 2       | `4d2dd7a`: rejected cleanup binds epoch and UID at execution; SDK mutations serialize with sign-in/sign-out. Listener generations, current SDK user identity, expired state and operation intents suppress stale callbacks/completions. Tests cover delayed cleanup after new sign-in, cleanup in progress, duplicate rejection, stale listener and stale sign-in.                                                                        |
| 3       | `4d2dd7a`: definitive disabled/deleted/expired/invalid-user/invalid-refresh errors expire only the current owner. Network refresh failure preserves the session and a later request recovers. Delayed old-owner failure and concurrent 401s cannot expire the new owner or run expiration twice.                                                                                                                                          |
| 4       | `4d2dd7a`: response JSON checks owner epoch before and after consumption. The generator preserves non-syntax JSON errors. Actual generated-client requests reject a switch during deferred successful and error JSON parsing.                                                                                                                                                                                                             |
| 5       | `4d2dd7a`: invalid modes throw; Firebase mode requires explicit well-formed HTTPS configuration without credentials/query/fragment. Both feature clients use that URL. The transport refuses unconfigured origins/paths before token acquisition or network transmission. Explicit local dev remains usable.                                                                                                                              |
| 6       | `f6dcf59`: Uvicorn access logging is disabled. The boundary logs only generated request ID, source route template/unmatched marker, status and duration. Unexpected exceptions become sanitized 500s before Uvicorn can log their representation. Sentinel tests cover path/query/header/body, unmatched/auth rejection, oversized bodies, SQL errors and generic exceptions.                                                             |
| 7       | `f6dcf59`: Alembic online executions acquire the same session advisory lock with a 30-second acquisition budget. Lock-query implicit transactions are rolled back before Alembic starts; caller-owned transactions are preserved. Error cleanup rolls back before unlock; broken unlock invalidates the connection. Four deterministic regressions pass; real PostgreSQL contention/aborted-transaction cleanup remains explicitly gated. |

The pinned Firebase Admin SDK now cryptographically verifies locally generated
RSA/X.509 fixtures through its actual ID-token verifier. Controlled certificate
and account-record responses cover valid identity, altered signature, expiry,
issuer/audience, revocation, disabled account and certificate outage; verification
itself is not mocked. The new signed two-subject integration test exercises
real owner resolution, separate same-email mappings, Profile/Event/Observation
CRUD/history/list isolation and Today. It is PostgreSQL-gated and has not run.

Latest checks: Python **90 passed, 43 PostgreSQL skips** (40 carried Phase 2,
identity race, signed two-subject route matrix, advisory-lock integration);
mobile **79 passed across 16 files**; Ruff, format, mypy, TypeScript, ESLint,
Prettier, scaffold, pip, compileall and reproducible OpenAPI/client generation
pass. Expo iOS export passes. `19fe52e` adds formatted HCL and the signed Google
8.2.0 lock for macOS ARM64/Linux AMD64; Terraform 1.13.3 backend-disabled init,
provider lock and schema validation pass. Exact commands/tool limitations are
in [release evidence](phase-3-release.md). No PostgreSQL, cloud apply/deployment
or spend occurred; Phase 3 live acceptance and Phase 4 remain gated.

Follow-up `e802439` invalidates the owner epoch before SDK sign-in can install
a different user, suppresses signed-out callbacks that could resurrect a
rejected account, and keeps failed sign-in retryable. Two more asynchronous
regressions pass; the final mobile count is 79.
