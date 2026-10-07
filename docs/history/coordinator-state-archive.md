> Archived coordinator notes. This file contains dated implementation-session
> state and is preserved only as history. It is not current status or policy;
> use docs/current-state.md and the linked release/review evidence.

# Historical implementation coordinator state

## Current checkpoint — October 5, 2026

The user explicitly authorized Phase 5 implementation on October 5. Local
Health-side consent, context preview, search, Assistant UI and documentation
are complete in logical commits: `1c82bd6` (API/data/contracts), `a2b9808`
(mobile), and `f939f35` (confirmation-aware context ranking). Release evidence
and this coordinator checkpoint are recorded with the current documentation
commit. A real Personal AI integration remains disabled because no provider,
service identity, delegation, tool-callback or retention contract was supplied.

Static verification passed: changed-file Ruff, mypy (32 API source files),
mobile TypeScript, ESLint, Prettier, OpenAPI export/client generation, Alembic
head/offline SQL generation, and `git diff --check`. A broader Ruff pass found
six import-order issues in unchanged API files; changed files are clean. No
tests were added or run. See [`phase-5-release.md`](../implementation/evidence/phase-5-release.md)
for commands, scope, limitations and open gates.

Do not claim live AI, clinical-safety, database-migration, cloud, or device
acceptance. The Phase 2 PostgreSQL migration/query gate, Phase 3 live
cloud/auth/storage parity, Phase 5 provider/retention/safety evaluation, and
mobile device/timezone/accessibility review remain open. Earlier Phase 4
acceptance limits are carried forward in its release evidence.

### Historical checkpoints

The following dated checkpoints preserve prior implementation decisions and
verification history. They do not supersede this current status.

## Previous stop checkpoint — October 4, 2026

The user requested finishing the current phase and stopping before the next
phase. Phase 3 local implementation and main-session review were complete
through `e802439`; Phase 3 local-only status and its unverified database/cloud
gates remain as historical context. The later October 5 request explicitly
authorized Phase 4.

Updated 2026-10-04 (PDT). Resume from this file, the phase plans, release evidence, and Git history; do not rely on conversation memory.

- Stage at the October 4 checkpoint: Phase 3 local implementation and seven review fixes were committed through `e802439`; P3.4 was offline IaC/runbook only, and P3.5 live acceptance was blocked on owner-supplied release inputs and staging. The user explicitly authorized skipping Phase 2's blocked database checks and continuing to Phase 3 on October 4. Phase 1 local review and Phase 2 code review were complete. Phase 2 database acceptance remains unverified (40 PostgreSQL tests, migration lifecycle/drift and query measurements); carry it forward before live release, without claiming it passed.
- Baseline: Phase 0 scaffold committed as `b06b93d` on `main`. This directory originally had no Git repository; Git was initialized to support the requested logical commits.
- Governing instructions: `CODEX.md`, `docs/handoff/codex-handoff.md`, `docs/implementation/phases/README.md`, and the current phase plan. The user's explicit request authorizes implementing Phases 1–9 sequentially, overriding the earlier Phase 0-only handoff boundary.
- Completed Phase 1 commits: `b491df0` (P1.1 schema/local principal), `433bc0d` (P1.2 PostgreSQL persistence/services), `4d1e365` (P1.3 Profile API/OpenAPI/generated client), `6f0b85b` (P1.4 mobile Profile flow/tests/docs), and `368ed43` (P1.5 release evidence and checks). Independent-review fixes are committed as `f75135d` (database payload identity checks) and `d388814` (mobile recovery, race, date, consent, and regression tests); the local-review checkpoint correction is `360d95a`.
- P1.4 delivers the accessible Profile-only shell, category-filtered/paginated overview, create/detail/edit/archive-confirmation/history routes, generated API client integration, revision-aware update/archive, explicit unknown/false/zero/date/unit/permission handling, and in-memory form retention on request failure. Review follow-up adds scoped pagination guards, dirty edit-draft retention, app-level uncertain-create recovery using the original ID/body, strict calendar validation, and cross-app/Personal AI permission wording. Simulator interaction/accessibility remain manual release gates.
- Latest validation after the review fixes (2026-10-03): API/domain/settings/persistence suite **42 passed** against a new disposable PostgreSQL 16.15 cluster. Three database-insert regression cases reject missing payload `kind`, `category`, and `key`. Alembic upgrade/downgrade/re-upgrade succeeded at head `4c168e5219d2`; `alembic check` found no model/migration drift. Mobile Vitest **23 passed** across six files; strict mobile TypeScript, ESLint, and Prettier passed. Ruff check/format, mypy (13 API source files), compileall, scaffold verification, and API-client TypeScript check passed. OpenAPI export and API-client regeneration produced no tracked diff. Expo SDK 57 iOS export succeeded with **1,121 modules** and a **2.4 MB** Hermes bundle; this is bundle evidence only, not device-rendering evidence. A new private temp cluster/database was removed after validation; the earlier unresponsive `/private/tmp/health-phase1-pg` cluster was left untouched.
- Release evidence is in `docs/implementation/evidence/phase-1-release.md`. It lists the six application tables, explicit indexes, routes, migration head, tests, implementation deviations, and all unverified gates.
- External/unverified gates: PostgreSQL 17/Docker; exact pnpm 9.15.0 frozen install and whole CI workflow (host exposes pnpm 11.19 only); on-device create/edit/archive/history, keyboard and VoiceOver walkthrough; Expo's online compatibility endpoint (offline local SDK-map check reports dependencies up to date); outstanding Phase 0 advisory/source-use review. Local DB tests use PostgreSQL 16.15. No claim is made that these gates passed.
- Baseline environment: Python 3.12.14 in `.venv`; bundled Node 24.19 at `/Users/jasonkli/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin`; local Expo export uses `EXPO_NO_TELEMETRY=1`. Docker and pinned pnpm are unavailable on this host. `scripts/verify_scaffold.py` must use `.venv/bin/python` (system Python 3.9 lacks `tomllib`). The Phase 0 review remains available under `docs/handoff/`.
- Agent policy: use `gpt-6-luna` with `xhigh` reasoning for every new phase/fix agent spawned before the scheduled restart on October 4, 2026 at 3:05 PM PDT (22:05 UTC); only agents spawned after that restart use `gpt-6-sol` with medium reasoning. Already-running agents finish their current work. `/root` owns coordination and independent review in the main session. After the restart, use a fresh Sol Medium agent for review fixes and have root light-verify them. Require tests, logical commits, a clean worktree, and `docs/implementation/evidence/phase-N-release.md` before moving to the next phase.

## Phase 2 scoped commits

Implement the complete Phase 2 plan sequentially: P2.1 daily schemas/time/units
and golden rollup fixtures; P2.2 additive Event/Observation persistence and
atomic compound commands; P2.3 resource/history/Today routes and generated
contracts; P2.4 manual Add/Today mobile flows and behavior tests; P2.5 integration
evidence/docs/CI. Preserve Profile contracts and all earlier data/history.
Extend Phase 1 envelope/revision constraints with additive migrations rather
than creating competing canonical stores. Extract only actually shared
identity/source/revision/error mechanics; avoid a generic JSON write API.
Blood-pressure pairs and symptom-linked observations require atomic compound
saves. Today must use DST-aware local-day bounds, overlap allocation, sparse
unknown/zero semantics, deterministic sum/latest rules, snapshot-consistent
paging and summaries, bounded queries, and revision references. No later-phase
planning/AI/cloud/native/web code. Require meaningful regressions for Profile,
owner isolation, retries, concurrent corrections, linked rollback, DST/date-only
semantics, unknown/zero, and mobile asynchronous recovery. Retain known external
gates as unverified; use a fresh disposable PG16 cluster for local DB tests if
PG17 is still unavailable.

- Restart reminders: the incorrectly anchored 2026-10-03 22:40 PDT entry was paused by `/root`; the corrected one-time restart fired on 2026-10-04 at 03:55 PDT (10:55 UTC). The next one-time restart is scheduled for October 4 at 3:05 PM PDT (22:05 UTC), automation id `resume-health-implementation-october-4-at-3-05pm-pdt`. Do not duplicate either automation.

## Phase 2 implementation checkpoint (2026-10-04)

- Phase 2 has started after reading the repository handoff, roadmap, detailed plan, Phase 1 evidence/review and inspecting current model/API/client/mobile sources plus Git state at `360d95a`.
- Reconciliation is recorded at the top of `phase-2-implementation-plan.md`. Phase 1 release evidence now accurately says local implementation and independent review are complete; all external gates remain open.
- Design uses the existing `health_objects`, `sources`, and `health_object_revisions` spine; Events/Observations will be typed owner-scoped subtypes with an additive migration. Revision snapshots will carry a serialized per-owner daily sequence to anchor a Today paging snapshot across future edits/archives. Daily source is server-owned `manual`, confirmation is `user_confirmed`; Profile behavior remains compatible.
- P2.1 is committed as `d46a139`: strict Event/Observation v1 JSON payload schemas are registered without changing Profile v1; `unit-v1` conversions and DST-aware day bounds are in `domain/daily.py`; fixed `today-v1` sparse rollups and a synthetic fall-DST golden fixture cover all five domains. Date-only rows keep their entered date and zone without inventing an instant; workout interval duration allocates by day overlap, while distance is assigned to its start day. Targeted validation: 31 domain/Profile-schema tests passed; Ruff, mypy, Ruff format and fixture Prettier checks passed.
- P2.2 is committed as `9a3f911`: additive migration `8e31c7c9a0b2`, Event/Observation/link models, shared manual-source and per-owner snapshot-sequence helpers, and transactional create/retry/update/archive/history service. Regression tests cover atomic symptom/severity saves, server-owned manual provenance and restrictive permissions, same-UUID retries/conflicts, blood-pressure pair writes, date-only persistence without an instant, rollback after an injected history failure, stale/concurrent updates, archive history, and cross-owner detail/link rejection. On PostgreSQL 16.15, the full API suite passes (**65 passed**); Alembic upgrade, empty-data downgrade/re-upgrade, and `alembic check` pass; changed-file Ruff check/format and mypy pass.
- P2.3 is committed as `d3aa0de`: Event/Observation create/retry/get/list/update/archive/history, atomic `/daily-entries`, and `/today`. Typed DTOs cover envelopes, history, resource pages, sparse summaries, and Profile context references. Today captures the owner's per-write sequence, resolves each indexed day candidate to its latest revision at or below that sequence, and computes timeline and summaries from those same rows. Cursors bind owner/date/timezone/sequence/key; later writes cannot change an issued Today snapshot. Resource lists use stable `(created_at, id)` keysets and bind date/timezone/type filters. Profile context appears only on page one. Seven daily API tests cover retries, history/archive/stale conflict, owner-scoped 404s, symptom-severity linkage and single counting, atomic blood-pressure writes, date-only precision, bounds, sanitized validation, snapshot continuation, and candidate caps. Their PostgreSQL integration run is pending. The API suite without `TEST_DATABASE_URL` reports **37 passed, 35 skipped**.
- P2.4 is committed as `fcf1010`: accessible Add forms for all five domains, Today summaries/timeline/profile context, item detail/edit/archive/history, Profile↔Today navigation, typed client use, and actual-component/model/recovery tests. Mobile Vitest reports **44 passed** across nine files; strict app/client TypeScript, ESLint (no warnings), whole-repository Prettier, and iOS Expo bundle export pass. The generated client exposes `HealthApiClient` and retains `ProfileApiClient` as a compatibility alias. Device, keyboard, visual layout, and VoiceOver remain manual gates.
- P2.5 evidence is recorded in `docs/implementation/evidence/phase-2-release.md`. The configured full CI Ruff check, Ruff format check (**36 files**), mypy (**21 sources**), compileall, scaffold check, OpenAPI export/client generation, and local iOS bundle passed. Alembic head is `8e31c7c9a0b2`. A prior PostgreSQL 16.15 P2.2 run passed **65 tests** and migration upgrade/downgrade/re-upgrade plus drift check; it does not substitute for the skipped P2.3 API routes or current query-cost evidence.
- Phase 1 evidence status was corrected after re-review: root's independent review is closed for local development, while PG17/Docker, exact pnpm9/full CI, device/VoiceOver, online compatibility, and Phase 0 advisory/source-use gates remain open.
- PostgreSQL follow-up: the documented test cluster at `/private/tmp/health-phase2-pg-20261003/data` was verified against exact PID **78748** and command line, then stopped gracefully with `pg_ctl` after the sandbox denied the normal signal. Restart and fresh PostgreSQL 16.15 `initdb` attempts still fail at `shmget` with OS shared-memory exhaustion. No unrelated process or shared-memory resource was touched. PostgreSQL-backed tests, migration lifecycle/drift, query plans, and database timing remain unverified until this host limit clears or another authorized disposable PostgreSQL instance is available. The failed fresh scratch directory is `/private/tmp/health-phase2-resume-pg`; the original disposable cluster remains stopped and contains only synthetic test data.

## Phase 2 independent-review fix checkpoint (2026-10-04)

- All eight findings in `docs/implementation/evidence/phase-2-review.md` were confirmed against code. Backend fixes are committed as `a24c48a`, mobile fixes as `435f396`; the review disposition and final verification checkpoint are included in the evidence commit.
- The plan records the resolved semantics: optional-end/date-only sleep; a `1e300` software ceiling for entered and canonical quantities with unit-aware conversion checks; severity coverage against active same-day symptom episodes; shared compound-write sequences and legal-boundary markers with a legacy-safe backfill; an indexed latest-revision lookup, 10,000-candidate cap and two-second PostgreSQL transaction-local timeout; draft/snapshot-scoped mobile state.
- Backend changes cover expected-type archive guards, shared compound sequences, the marker model and additive migration, Today read/rollup orchestration, bounded numeric conversion/sums, sleep and severity semantics, and regressions for DELETE, rollback, sequence boundaries, overflow and coverage. Mobile changes retain daily edit drafts/revision baselines, preserve editable interval ends and units, support partial sleep, reject stale Today page responses and reset history pagination on scope change.
- Latest local results: `pytest -c services/api/pyproject.toml services/api/tests -q` **39 passed, 40 skipped**; `test_daily_domain.py` **19 passed**. Mobile Vitest **54 passed across 11 files**, strict app and generated-client TypeScript passed, ESLint passed, and whole-repository Prettier passed after evidence edits. Configured CI Ruff check, Ruff format (**36 files**), mypy (**21 sources**), compileall and scaffold verification passed. Expo SDK 57 iOS export bundled **1,136 modules** into a **2.5 MB** Hermes bundle.
- OpenAPI export/client regeneration passed; the intended contract diff is the new `FiniteDailyNumber` alias for daily numeric values. Alembic has one head, `b9f5e1a72c4d`; offline upgrade SQL generation passed. These do not substitute for a live migration lifecycle or model-drift check.
- The new isolated PostgreSQL 16.15 `initdb` path failed twice at bootstrap with `shmget(..., size=56) ENOSPC`; each failed data directory was removed by `initdb`. The config override still selected System V shared memory before bootstrap. The sandbox denied `ps`; `ipcs -m` listed no segments but reported a system-query permission limitation. No initialized cluster was started and no other cluster or shared IPC was touched. PostgreSQL route/persistence tests, migration lifecycle/drift, EXPLAIN/ANALYZE and latency remain unverified.
- At that Phase 2 review checkpoint, root's independent code re-review was complete; details and accepted dispositions are in `phase-2-review.md`. One residual string-to-float numeric-bound bypass was reproduced and fixed by moving the magnitude check after Pydantic coercion. Three regressions pass. Root reran the API suite (**42 passed, 40 skipped**), mobile suite (**54 passed**), configured CI Python static/scaffold checks, mobile TypeScript/ESLint and client TypeScript. OpenAPI/client regeneration had no tracked diff. The following Phase 3 checkpoint supersedes the then-current statement that Phase 3 had not started.
- Next action requires a usable authorized disposable PostgreSQL instance (or restored host shared-memory capacity). Set `TEST_DATABASE_URL` to its test database, run all 82 Python tests, exercise fresh and existing-data migrations at head `b9f5e1a72c4d`, check drift, and measure Today query plans/latency on sparse and high-revision histories. Delegate substantive failures to a fresh Luna Extra High agent, then root re-review and close Phase 2 before scoping Phase 3. Preserve all external device/PG17/pnpm/Phase 0 gates accurately.
- Resume check on October 4 at 10:03am PDT: clean repository at `7cc0a7d`. Fresh PostgreSQL 16 initialization at `/private/tmp/health-phase2-recheck.LMWy24/data` failed both inside and outside the sandbox with `shmget(..., size=56)` / `ENOSPC`; the elevated attempt selected POSIX dynamic shared memory but still failed allocating the main shared-memory segment. `initdb` removed both failed data directories. No server started, no other cluster/IPC was touched, and no Phase 3 work began. The same database acceptance blocker still requires host capacity recovery or an authorized disposable database.

## Phase 3 implementation checkpoint — October 4, 2026

- Local implementation is committed through `c288982`: `d041477` strict settings/provider identity mapping; `95d7c3d` Firebase backend auth, typed bearer contract, and real mobile Firebase SDK session lifecycle; `0708109` path-safe local/GCS object adapters and non-root hash-locked API container; `c288982` explicit GCP Terraform/Cloud Build artifacts and migration-first rollback runbook. P3.4 is offline artifacts only. P3.5 live acceptance is not complete, and this checkpoint does not advance Phase 4.
- Full release evidence is in [`phase-3-release.md`](../implementation/evidence/phase-3-release.md). The final API test run reports **77 passed, 41 skipped**: 40 carried Phase 2 PostgreSQL cases (`daily_api` 12, `daily_persistence` 6, `profile_api` 9, `profile_persistence` 13) plus one new skipped `test_provider_identity_persistence.py` first-login race. The PostgreSQL gate still includes full route/persistence tests, migration lifecycle and drift checks, and query profiles. The documented prior `initdb` ENOSPC remains the blocker; no new initdb or unrelated cluster/IPC attempt was made.
- Python Ruff check passed, Ruff format check found 43 files formatted, mypy found no issues in 24 source files, scaffold verification and pip checks passed, and the hashed production lock dry run passed. Mobile has **60 passing tests**, strict TypeScript, ESLint and whole-repository Prettier pass; exact pnpm 9.15.0 frozen install succeeded from the local cache with zero downloads; Expo iOS export bundled 1,157 modules into a 2.9 MB Hermes bundle. OpenAPI/client regeneration produced no diff. Offline Alembic SQL reached `c3721f5a9a01`, but is not database migration evidence.
- IaC/build boundaries: Terraform/OpenTofu, gcloud, Docker and Podman are unavailable; HCL formatting, validation and provider-lock generation are unverified. Cloud Build YAML parsing, builder-script syntax/argument guard and offline SQL generation passed. No live Firebase users/project, Neon endpoints/secrets, GCP project/region, private bucket/retention policy, approved spend budget, instance/connection budget or state bucket was supplied. No cloud operation or spend occurred. See the evidence file for official vendor sources checked 2026-10-04 and exact commands.
- Resume sequence: first obtain an authorized disposable PostgreSQL instance, set `TEST_DATABASE_URL`, run all currently skipped tests and the Phase 2 migration lifecycle/drift/query checks, and close that deferred gate. Independently obtain owner-approved non-secret release identifiers and approved secret names/versions/budget, install Terraform/OpenTofu and gcloud under normal tooling policy, generate/commit provider lock, validate and review a plan, then request any required external apply approval only after a concrete plan. Deploy migration Job before API service and run the real two-user, owner isolation, GCS privacy, connection, shutdown, rollback and cost/log-redaction acceptance. Do not begin Phase 4 until root re-review and release acceptance are complete.
- Agent timing: every new phase/fix agent spawned before October 4, 2026 3:05 PM PDT / 22:05 UTC remains `gpt-6-luna` Extra High. Only agents spawned after that scheduled restart use `gpt-6-sol` Medium. The one-time restart automation is `resume-health-implementation-october-4-at-3-05pm-pdt`; do not duplicate it. The main session owns independent review; after restart, use fresh Sol Medium agents for review fixes, then root light-verifies.

## Phase 3 review-fix checkpoint — October 4, after 15:05 PDT

- Review baseline `8b6c093`; earlier uncommitted edits were preserved/finished
  by the fresh Sol Medium fix agent. Logical commits: `4d2dd7a` mobile key
  mapping/session races/token invalidity/JSON/config; `f6dcf59` privacy logging,
  PostgreSQL advisory release lock, actual signed Firebase SDK fixtures and
  gated two-subject owner routes; `19fe52e` formatted/validated Terraform and
  signed Google 8.2.0 lock for macOS ARM64/Linux AMD64. All seven dispositions
  are in `evidence/phase-3-review.md`; root independent re-review remains next.
- Latest API **90 passed, 43 skipped**: 40 deferred Phase 2 cases plus first-
  login identity race, signed two-subject route isolation and real advisory-
  lock contention/cleanup. Mobile **79 passed/16 files**, strict app/client
  TypeScript, zero-warning ESLint, Prettier, Ruff/format (**48 files**), mypy
  (**26 sources**), compileall/scaffold/pip checks and reproducible generation
  pass. Expo iOS export: **1,158 modules**, **2.9 MB**. Offline SQL head remains
  `c3721f5a9a01`; no live migrations/database claim.
- Terraform 1.13.3 was safely acquired and checksum-verified in `/private/tmp`.
  Backend-disabled init and signed Google 8.2.0 platform lock, HCL format and
  schema validation pass. Default sandbox DNS and local plugin-handshake
  limitations were resolved through authorized elevated local tooling, not
  treated as permanent blocks. No backend/cloud/apply/plan/spend occurred.
- Resume: root light-reviews fixes and checks clean committed evidence; obtain
  usable authorized disposable PostgreSQL and run all 133 Python cases plus
  deferred Phase 2 migration lifecycle/drift/query measurements and lock/owner
  checks. Owner release identifiers/secrets names/versions/budget remain
  pending; no guessed project or identity. Then review a concrete Terraform
  plan and authorized staging migration-first release, live two-user auth,
  GCS privacy, redacted logs, connections/shutdown/rollback/cost gates. Do not
  claim Phase 3 live completion or advance Phase 4.

Follow-up `e802439` invalidates the owner epoch before SDK sign-in can install
a different user, suppresses signed-out callbacks that could resurrect a
rejected account, and keeps failed sign-in retryable. Two more asynchronous
regressions pass; the final mobile count is 79.
