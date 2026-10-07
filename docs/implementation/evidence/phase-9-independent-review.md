# Phase 9 independent review — Luna XHigh handoff and remediation

Reviewed October 7, 2026: `70ed887db1f0567ff8b2dd969139d213ff12d752`
against parent `ca1eef2`, the reconciled Phase 9 plan, current-state/release
records, product/architecture/privacy intent, migrations, application code,
storage/auth/client boundaries, and mobile integrations. No substantive fixes
were made in that review. This document preserves its findings and records the
follow-up work.

At review time, the implementation was **not yet sound enough for acceptance**. Its explicit
owner inventory, snapshot export, dependency-ordered erasure, retained identity,
disabled document ingress, and honest scope reconciliation are sensible.
Remaining defects and verification gaps are below. P1 means address before
accepting the affected capability; P2 means a concrete correctness/recovery
issue requiring follow-up. Inherited issues are identified separately.

## Remediation status — October 7, 2026

The follow-up addressed the executable findings and committed regression
coverage. This resolves the listed local defects; it does not close the
separate Phase 9 release gates described later in this record.

| Finding                                          | Follow-up result                                                                                                                                                                                                                                                                                                                          |
| ------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1. Checkpoint-key bounds and malformed inventory | Fixed bounds and key validation; malformed inventories fail closed and cleanup preserves its retry inventory. Mobile tests cover realistic identities, owner isolation, repeated saves, malformed indexes, and interrupted deletion.                                                                                                      |
| 2. Retryable local cleanup                       | Added ordered retryable cleanup state, initial storage-error handling, and recovery gating. Tests fail each cleanup step and retry without losing intent.                                                                                                                                                                                 |
| 3. Session/account switch fencing                | Bound sign-out to the captured session epoch and owner; fenced export/share completion and screen updates.                                                                                                                                                                                                                                |
| 4. Recent-auth transport handling                | Preserve structured API errors; recent-auth/principal lifecycle errors bypass token refresh and session expiry. Tests cover both 401 classes and invalid-token refresh behavior.                                                                                                                                                          |
| 5. Lost request-ID recovery                      | Added recent-authenticated `GET /deletion-requests/current`, generated-client support, and mobile recovery from server discovery. PostgreSQL API tests cover resume, completion, owner isolation, and conflict behavior.                                                                                                                  |
| 6. Concurrent identical starts                   | Serialize request IDs and recheck under lock. A PostgreSQL concurrency test confirms same-ID replay while foreign-ID collisions remain hidden.                                                                                                                                                                                            |
| 7. Bounded object cleanup                        | GCS cleanup uses a 240-second configured timeout budget per request and remains resumable. Adapter tests verify batch size, generation conditions, timeout propagation, and repeated batches; live GCS remains unverified.                                                                                                                |
| 8. Destructive behavior coverage                 | Added PostgreSQL tests that seed all 25 owner tables, verify export ownership and row/UTF-8 limits, assert zero owner rows after erasure while preserving a second owner, exercise write freeze and downgrade refusal, and test recent-auth/recovery/concurrency paths. Mobile tests cover checkpoint and local-cleanup failure recovery. |
| 9. Proposal event/revision ordering              | Added explicit revision flush boundaries in create/edit paths; the full PostgreSQL suite now exercises the repaired proposal paths.                                                                                                                                                                                                       |
| 10. Search projection crash                      | Split SQL-expression and decoded-payload projections while retaining the same relationship-field exclusions; matching search is exercised by the PostgreSQL suite.                                                                                                                                                                        |
| 11. Regression assertions                        | Corrected analytics call arguments, flat HealthKit error assertions, deterministic daily history ordering, the safe `distance` field path, zero-valued observations-only symptom-summary semantics, and aggregate receipt counts. The full PostgreSQL suite passes without weakening privacy or unknown-versus-zero behavior.             |
| 12. Migration drift                              | Added a narrow semantic comparator for four equivalent GIN expressions. Comparator tests keep missing or materially changed indexes visible; `alembic check` reports no upgrade operations on PostgreSQL 16.15. PostgreSQL 17 and query-plan checks remain open.                                                                          |

## Findings in the delivered account-data slice

### 1. P1 — Checkpoint cleanup silently discards realistic keys

**Files:** `apps/mobile/src/integrations/healthkit/checkpoint.ts:68`,
`checkpointKey.ts`, `secureKey.ts`.

`save()` indexes unrestricted encoded keys, but `loadKeys()` rejects the entire
index if any key exceeds 256 characters and returns `[]`. A 28-character account
ID and UUID installation ID produce a 322-character steps checkpoint key.
A synthetic probe saved that checkpoint, called `clearOwner()`, and observed
the checkpoint still present while the index became `[]`. Subsequent saves can
also lose previously indexed keys. This contradicts the erasure guarantee even
though the native importer remains disabled today.

**Fix:** use bounds consistent with supported encoded identities; validate on
both write/read. Invalid indexes must not be treated as successful empty
cleanup. Preserve recoverability rather than overwriting the only key inventory.
**Validate:** realistic/max-length identities, multiple accounts/installations,
repeated saves, malformed indexes, storage interruption, and complete removal
of only the selected owner's entries.

### 2. P2 — Server completion disables retry before local erasure succeeds

**File:** `apps/mobile/src/features/account-data/screens/AccountDataScreen.tsx:76,122`.

Both status-loading and submission set `deletionStatus = completed` before
`finishDeletion()` clears consent/checkpoints. A SecureStore failure leaves
local data and the request key, but both buttons are disabled and the screen
offers no local-cleanup retry. Initial `getItemAsync()` is also outside the
effect's error handler; recovery can fail with an unhandled rejection. Controls
remain enabled while the saved request is being loaded, permitting a second
request to overwrite its recovery key.

**Fix:** distinguish server completion from pending/completed local cleanup;
retain a retryable cleanup intent until all local work succeeds. Handle initial
storage errors and gate destructive actions until pending-request loading ends.
**Validate:** fail each local operation individually, retry without remounting,
restart midway, and delay initial key loading while attempting submission.

### 3. P2 — Completion side effects are not fenced to their original session

**File:** `apps/mobile/src/features/account-data/screens/AccountDataScreen.tsx:54`.

`finishDeletion()` awaits several storage operations and then calls global
`signOutCurrentUser()`. If account A's screen unmounts and B signs in during
cleanup, A's continuation can sign B out. The effect's `active` check happens
before cleanup; layout remounting and authenticated-fetch guards do not cancel
these later side effects.

**Fix:** capture the session epoch/account, recheck before global session/UI
effects, and use an owner-bound sign-out. Cleanup for A may continue without
changing B's session. **Validate:** switch A→B during every awaited cleanup
step; B must retain its session and secure state. Apply equivalent fencing to
export/share completion where needed.

### 4. P2 — Recent-auth errors are swallowed by the mobile transport

**Files:** `apps/mobile/src/auth/authenticatedFetch.ts:133`,
`features/account-data/screens/AccountDataScreen.tsx:30`,
`services/api/src/health_api/api/account_data.py:49`.

The new API returns `401 recent_authentication_required` for a valid but old
login. Transport retries every 401 with token refresh, expires the session, and
throws `ApiError(401)` without its body. Refresh does not refresh `auth_time`.
The screen's specific reauthentication message is therefore unreachable.
A synthetic transport probe confirmed two sends, session expiration, and an
undefined error body.

**Fix:** distinguish valid-session reauthentication/domain-lifecycle failures
from invalid-token failures; preserve sanitized structured error bodies and
guide the user through reauthentication while retaining the request UUID.
**Validate:** old/missing/future `auth_time`, actual invalid tokens, refreshed
tokens with unchanged `auth_time`, and successful same-request continuation.

### 5. P2 — Losing the client UUID strands a frozen owner's erasure

**Files:** `services/api/src/health_api/application/account_data_service.py:185`,
`api/account_data.py`, mobile account-data recovery.

After the write freeze, another UUID gets a conflict and status requires the
original UUID. There is no authenticated discovery of the owner's existing
job. Reinstall, device loss, or starting from another device leaves a user
unable to resume request-driven deletion or determine completion. The durable
server job is insufficient if its only recovery handle exists on one device.

**Fix:** provide an owner-authenticated way to retrieve/resume the existing
erasure job, keeping explicit recent authentication and ownership checks.
Do not introduce a queue merely to solve discovery. **Validate:** lose local
storage after freeze, resume from a second client, completed-job recovery,
foreign-owner isolation, and conflicting request IDs.

### 6. P2 — Concurrent identical starts violate idempotent replay

**File:** `services/api/src/health_api/application/account_data_service.py:188`.

The job lookup occurs before the owner lock. Two starts with the same UUID can
both see no job; after waiting for the first commit, the second sees a deleting
owner and raises conflict instead of returning the first job. A synchronized
PostgreSQL probe returned `running` and `AccountDataConflict` for identical
requests. Retrying later works, but overlapping timeout retries should replay.

**Fix:** recheck the job after acquiring the serialization lock, or use an
equivalent race-safe creation/replay pattern. Keep different-owner UUID
collisions and genuinely different requests distinct. **Validate:** concurrent
same UUID, different UUID, foreign-owner collision, and completion/retry races.

### 7. P2 — Object cleanup has a count bound but no request-time bound

**Files:** `services/api/src/health_api/integrations/object_storage.py:370`,
`application/account_data_service.py:234`, `infra/gcp/main.tf:86`.

The GCS adapter performs up to 1,000 sequential deletions, each with the
configured 10-second timeout, plus listing. Even successful 0.5-second deletes
exceed the configured 300-second Cloud Run request timeout. Count bounds do not
make this a bounded HTTP step; a client can time out while work continues and
start overlapping processors.

**Fix:** add an overall cleanup deadline/smaller batch suitable for the HTTP
budget, returning pending after completed work. Preserve generation checks and
retry semantics; choose background processing only if demonstrated necessary.
**Validate:** slow successful deletes, failures midway, listing pagination,
more than 1,000 generations, timeout retry overlap, and real synthetic GCS
acceptance before cloud claims.

### 8. P1 acceptance gap — Destructive phase 9 behavior has no committed tests

**Files:** new account-data service/routes/migration, mobile account-data screen,
checkpoint cleanup, and `services/api/tests` / `apps/mobile/tests`.

The commit changes 30 files and adds no tests. Existing suites do not exercise
export, owner erasure, recent-auth routes, or the new cleanup methods. Static
inventory matching does not prove every populated table is erased or exported;
the checkpoint defect escaped all 115 existing mobile tests.

**Fix/validate:** add focused behavioral coverage in test directories: populate
all 25 inventory tables and dependent histories/receipts; exact owner export and
zero post-erasure counts with another owner preserved; row/UTF-8-byte limits;
repeatable-read consistency under concurrent mutation; write-freeze races;
failed/interrupted cleanup and replay; migration upgrade/downgrade refusal;
recent-auth and foreign-job routes; local/GCS generation cleanup; and findings
1–7's mobile/concurrency regressions. Verify actual PostgreSQL behavior rather
than replacing it with SQLite or mocks. Keep live cloud/device gates explicit.

## Inherited issues relevant to Phase 9 system hardening

### 9. P1 — Proposal creation flushes an event before its referenced revision

**Files:** `services/api/src/health_api/application/action_proposal_service.py:702`,
`persistence/models.py` proposal revision/event mappings.

The locked SQLAlchemy version is 2.1.3. In the real-database tests, creation
adds a revision and event then flushes; the event is inserted first and violates
`fk_action_proposal_events_revision`. The service misreports this as a reused
proposal ID. Both database proposal tests fail before testing apply rollback
or ownership. The same failure occurs on the parent commit; Phase 9 did not
introduce it. This also blocks the planned extraction-as-proposal integration.

**Fix:** guarantee referenced revisions are persisted before events, through
an explicit flush boundary or actual ORM dependencies; audit update paths for
the same ordering. Preserve one outer atomic transaction. **Validate:** both
failing Phase 6 database tests, create/update/reject/apply/replay, and rollback
after target writes, using the locked environment.

### 10. P2 — Search with matching rows raises instead of returning results

**File:** `services/api/src/health_api/application/ai_context_service.py:776`.

Result construction passes decoded `row.payload` into
`_payload_search_projection()`, which expects a SQL expression and calls `.op()`.
A synthetic matching Event produces `AttributeError: 'dict' object has no
attribute 'op'` and API `500 internal_error`; an empty result succeeds. This is
also present on the parent commit.

**Fix:** use a separate in-memory projection with the same relationship-field
exclusions as the SQL projection. **Validate:** matching Profile/Event/
Observation/planning rows, excluded relationship text, owner/permission
filtering, paging, and the existing context/search permission-revision test.

### 11. P2 verification gap — Reconcile the remaining failing regressions

**Files:** `test_analytics_review_regressions.py`, `test_healthkit_import_api.py`,
`test_daily_api.py`, `test_daily_persistence.py`, `test_ai_context_api.py`.

Beyond findings 9–10, eight suite failures undermine the planned whole-system
hardening evidence. Two analytics tests omit new `_standard_points` arguments;
two HealthKit tests expect a nested `error` although the contract is flat;
the daily history test orders only by a sequence shared by multiple objects
and sometimes inspects the Observation as an Event. The remaining assertions
concern numeric validation field paths, an observations-only symptom-summary
row, and aggregate recomputation's created/updated receipt count.

**Fix:** reconcile assertions with executable contracts and intended behavior,
without weakening privacy/provenance or aggregate-restoration requirements.
For the three remaining assertions, determine whether the implementation or
test is wrong before changing either; the failure alone is not proof of a
production defect. **Validate:** run the full database suite repeatedly, check
the actual recomputed Today value after tombstoning, preserve unknown-versus-
zero semantics, and verify relationship-safe AI summaries.

### 12. P2 verification gap — Migration drift check currently fails

**Files:** `migrations/env.py`, `persistence/models.py` AI search indexes,
prior search-index migrations.

On the disposable migrated PostgreSQL 16.15 database, `alembic check` proposes
dropping/recreating four AI search indexes because reflected PostgreSQL casts
and ORM expression rendering differ. The affected definitions are unchanged
by Phase 9. This may be equivalent-expression comparison noise; it is not
evidence that indexes are missing or functionally wrong.

**Fix:** establish semantic agreement and make the drift gate reliable with a
narrow comparison/model correction if appropriate. Do not recreate working
indexes just to silence the check. **Validate:** clean upgrade and drift check
on the documented PostgreSQL 17 baseline, index definitions and representative
query plans, plus the two Phase 9 tables and triggers.

## Plan completion boundaries, not newly discovered implementation defects

The written reconciliation correctly labels this as a partial P9.4 foundation.
Do not treat these declared omissions as permission to implement the entire
remaining phase during defect follow-up:

- **P1 before recovery/complete-erasure acceptance:** verified backup retention,
  encrypted portable backup/object manifest, isolated restore, a deletion ledger
  available independently of an old restore, replay before serving, measured
  RPO/RTO, and precise external-copy retention/deletion obligations. The current
  database-only marker cannot prevent resurrection from an older backup.
- **P1 before document ingress:** complete store/retention inventory, quarantine/
  scanner and isolated parser policy, immutable record lifecycle and orphan
  reconciliation, reviewed extraction contract, typed lab proposals/evidence,
  and Records review UI. Keep ingress and live extraction disabled meanwhile.
- **P2 planned product work:** durable large-export/download/expiry handling and
  explicit fresh domain-principal enrollment/consent after erasure. Current
  caps and permanently blocked retained principals are disclosed limitations.
- **P1 before whole-system release:** resolve executable hardening findings,
  synthetic performance/security/log-canary checks, dependency review, and
  actual cloud/device/accessibility/account-switch/E2E acceptance. There is no
  evidence supporting complete Phase 9 or ecosystem erasure today.

## Verification at review time

- Initialized isolated PostgreSQL **16.15** under `/private/tmp`; applied all
  migrations through `20261007b1c2`. This does not establish PostgreSQL 17,
  Neon, Firebase, GCS, or device acceptance.
- Full API suite: **202 passed, 11 failed**. Independently archived and tested
  the parent in a second disposable database: **the same 11 failures**.
- Full existing mobile suite: **115 passed** using installed Vitest directly.
  The available `pnpm` was 11.25.0, outside the repository's required 9.x;
  no dependencies or lockfiles were changed.
- Synthetic PostgreSQL probes: export of a populated owner covered the 25-table
  manifest; simple erasure left zero inventoried owner rows and preserved a
  second owner's rows/objects; frozen writes failed with SQLSTATE `23514`;
  10,001 source rows yielded `running` with one remaining row, then `completed`
  with zero; simultaneous same-UUID starts reproduced finding 6.
- Transpiled adapter/transport probes reproduced findings 1 and 4. These were
  in-memory SecureStore/fetch probes, not native-device tests.
- `alembic check` failed as described in finding 12. No full-table populated
  erasure, export-race, provider, backup/restore, or native acceptance claim is
  made from the small probes. Source inspection supports the other findings.

## Follow-up verification and limits

- Full API suite against an isolated PostgreSQL **16.15** database after all
  follow-up changes: **221 passed**, with one Starlette/httpx deprecation
  warning. The suite includes all 25 owner tables, export/erasure ownership,
  row and UTF-8 byte limits, repeatable-read behavior under concurrent edit,
  write freeze, idempotent deletion recovery/concurrency, migration downgrade
  refusal, proposal ordering, search, and regression fixes.
- Full mobile Vitest suite: **125 passed** across 25 files. Mobile TypeScript
  typecheck passed.
- `alembic check` on the same PostgreSQL 16.15 database reported no new
  upgrade operations. Comparator tests confirm that missing or changed GIN
  definitions are still reported.
- The generated OpenAPI artifact and TypeScript client were regenerated and
  typechecked. Focused Ruff checks and formatting passed.
- GCS cleanup tests use a fake client and establish configured deadline and
  generation-precondition behavior only. No live GCS, Neon, Firebase, iOS,
  HealthKit, external-AI retention, PostgreSQL 17, restore/replay, accessibility,
  performance, or whole-system release acceptance is claimed.

The code defects and regressions listed in findings 1–12 now have follow-up
fixes or corrected assertions. Preserve the architecture and disabled-feature
gates. Phase 9 remains open for the backup/restore, deletion-ledger replay,
record-ingress, external-retention, cloud, and device gates above; do not infer
complete Phase 9 acceptance from this local remediation.
