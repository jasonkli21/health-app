# Phase 1 independent review

Main-session review, 2026-10-03 PDT, implementation through `368ed43`.
Reviewed Phase 1 plan, roadmap, product/UX/security/data/architecture/ADRs,
domain/config/application/persistence/migrations, HTTP contract/middleware/errors,
client generator, mobile screens/form/model, tests and CI. All six findings below
were confirmed in the reviewed code and are addressed in the follow-up changes.
Independent re-review by `/root` is complete for local Phase 2 development.
The external release gates listed below remain open.

Re-review checked the changed screen wiring, shared request guard, dirty-draft
state, original-create recovery, SQL constraint migration, regression tests,
and compatibility with the existing Profile contract. A small residual fix
preserves server microsecond timestamps and compares submillisecond validity
windows, and disables conflict reload while saving. The main session reran
24 mobile tests, strict TypeScript and ESLint successfully; 20 backend tests
passed with 22 database cases explicitly skipped (no running test database).
The fix agent's fresh 42-test PostgreSQL run remains the database evidence.
Ruff import/format discrepancies found in re-review were corrected; Ruff,
mypy (15 source files), and scaffold checks pass. No unresolved code finding
blocks the next local implementation phase.

## Required fixes and implementation disposition

1. **Addressed — pagination request races (P2).** Overview `loadMore` and history `loadMore`
   lack the lifecycle guard used by initial fetches. Change category, refocus,
   reload or change item while an old page is pending and its response can append
   stale entries and overwrite the current cursor/error/busy state. Bind every
   page result to a request generation/scope, invalidate on reset/blur, and avoid
   duplicate concurrent page requests. Cover delayed out-of-order responses.
   `requestScope.ts` now guards both screen page requests by active scope and
   generation, and suppresses duplicate in-flight cursor requests. Regression
   tests cover category changes, refocus, reload, item switches, blur, stale
   success/error results, and duplicate taps in
   `apps/mobile/tests/profile-request-scope.test.ts` (7 cases).
2. **Addressed — edit draft loss (P2).** Edit sets `loading=true` on every focus/refetch;
   rendering then unmounts `ProfileForm`, losing its internal draft, including a
   failed-save draft. Retain dirty/failed drafts in memory across background
   refreshes and failed reloads. Replace a draft/revision only in an explicit
   successful conflict-reload flow or after save/cancel. `editState.ts` keeps a
   dirty draft and its revision, while `ProfileEditScreen` leaves the form mounted
   during background refreshes and reload failures; only clean refreshes or a
   successful explicit conflict reload reset the form. Tests cover dirty/clean
   refresh and conflict reload in `apps/mobile/tests/profile-edit-state.test.ts`
   (4 cases).
3. **Addressed — ambiguous create recovery (P2).** Create reuses one ID for every body. A
   committed POST whose response is lost followed by a changed draft produces a
   permanent different-content 409; the form cannot recover or reach the created
   item. Preserve the original request identity/content for uncertain retries;
   provide an explicit recovery route to reconcile that original save before
   submitting edited content. Do not fix by blindly minting another ID, which
   duplicates a potentially committed health item. An in-memory app-level recovery
   record retains the uncertain request ID and fields across route unmounts. The
   form blocks changed-body submission until an explicit “Retry original save”
   recovers the prior result; known 4xx validation failures remain editable.
   Tests cover a lost response, changed draft, exact-body retry, 422 correction,
   and uncertain 503 response in
   `apps/mobile/tests/profile-create-recovery.test.ts` (3 cases), with the recovery
   action also covered by the accessible form render check.
4. **Addressed — permission consent wording (P2).** Form says cross-domain permission allows
   use in 'other health areas'; the architecture defines sharing with other apps
   and domains through Personal AI. The form now names use by other apps and health
   domains through Personal AI in visible and accessibility text; detail and
   history show the same scope. Both switches remain off by default, covered by
   `apps/mobile/tests/profile-form.render.test.tsx`.
5. **Addressed — silent temporal normalization (P2).** `parseInstant` trusts JavaScript Date,
   which normalizes impossible dates such as February 30 into a different day.
   The parser now validates ISO date, time, timezone-offset, month length, and leap
   day bounds before converting to UTC. Tests reject invalid days/months/leap dates
   and out-of-range times/offsets and accept a valid leap day with an offset in
   `apps/mobile/tests/profile-model.test.ts`.
6. **Addressed — database JSON check null loophole (P2).** The payload-consistency CHECK uses
   SQL equality against missing JSON fields; SQL NULL passes CHECK. Ensure a
   malformed object with missing kind/category/key cannot pass the intended
   consistency constraint. Use explicit existence/non-null checks or IS TRUE,
   keep ORM/migration agreement and test direct malformed DB inserts. The ORM
   constraint and migration `4c168e5219d2` now require the three JSON fields to
   exist as strings before comparing them. Three direct database insert tests
   verify a missing `kind`, `category`, or `key` fails the CHECK; `alembic check`
   reports no model/migration drift. SQL still checks identity consistency only,
   not the complete Pydantic payload schema.

## Verification and completion requirements

The requested regression tests, fresh disposable PostgreSQL integration run,
migration lifecycle, static checks, generated-contract check, and iOS bundle
export were completed. Exact results and the remaining external/device gates are
recorded in [Phase 1 release evidence](phase-1-release.md). The main-session
independent review and re-review are complete, with no local finding blocking
Phase 2 implementation. This does not close any external or native-device gate.

Known external gates remain PG17/Docker, exact pnpm9/full CI, actual device and
VoiceOver/keyboard walkthrough, online compatibility, and Phase 0 advisories.
No cloud/AI/native/web capabilities belong in this fix scope. The final review
disposition is recorded in the Phase 2 checkpoint. Future implementation should follow current repository guidance and the active user request.
