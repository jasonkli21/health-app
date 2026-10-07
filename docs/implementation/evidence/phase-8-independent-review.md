# Phase 8 independent review — Luna XHigh handoff

Reviewed October 7, 2026: `72cb08de4f8f4d7a1f1039573f6e52a34147dcf2`, compared with parent `1eccb4d`. No implementation fixes were made.

The foundation is **not yet sound**. Address the findings below before enabling native import. Preserve the documented disabled adapter: native library/build/entitlements, real-device permissions/aggregation/deletions, and background behavior remain separate acceptance gates. Their absence is honestly documented rather than an undisclosed implementation defect.

Scope: phase 8 plan/reconciliation and release evidence; product, data, security and mobile intent; complete commit diff; import contracts/routes/service/persistence/migration; mobile mappings/settings/consent/checkpoints/coordinator; daily writes/history, Today, analytics, AI context, tests, OpenAPI and client integration. P1 = high priority correctness/privacy blocker; P2 = required correction or acceptance gap. Paths below are repository-relative; API application/domain paths begin `services/api/src/health_api/`, and mobile integration paths begin `apps/mobile/src/integrations/healthkit/`.

1. **P1 — Every secure-storage key is invalid.**
   Files: mobile `consent.ts:7–15`, `checkpointKey.ts:9–16`, `checkpoint.ts`.
   Consent, lookback and checkpoint keys contain `:`. The installed `expo-secure-store/src/SecureStore.ts:229–238` rejects anything outside `^[\w.-]+$` before calling native storage. All settings reads/writes fail; acknowledged syncs cannot durably save anchors. The memory-store tests conceal this.
   Fix: use a deterministic, collision-safe encoding within the supported key alphabet, including arbitrary owner IDs; retain account/type/installation/policy isolation.
   Validate: exercise actual key validation and consent/lookback/checkpoint round trips, storage failures, and different accounts. Device persistence remains a real-device gate.

2. **P1 — Sleep import produces incorrect duration.**
   Files: mobile `mapping.ts:122` (`mapSleep`); API `application/healthkit_import_service.py` sleep validation; `domain/daily_rollups.py:228–240`; Today/analytics input construction.
   `awake` is accepted and mapped to an ordinary sleep Event. Stage metadata never reaches the rollup, which sums every interval, including overlapping stages/providers. PostgreSQL/API probes yielded 60 sleep minutes for one hour of awake data and 120 minutes for two records occupying the same hour. The plan explicitly prohibits additive overlapping sleep sources.
   Fix: carry stage/source semantics through representative selection; exclude awake from asleep duration and apply a declared overlap/source policy. Preserve imported records/history and manual sleep semantics.
   Validate: awake-only, disjoint stages, generic asleep overlapping detailed stages, competing providers, cross-midnight/DST, updates/deletes, and matching Today/trend/consented-context outputs.

3. **P1 — Selecting an installation still double-counts timezone variants.**
   Files: API `application/healthkit_import_service.py:457–480`, `set_healthkit_source_preference`; `application/today_service.py:119`; `application/analytics_service.py:_load_inputs`; `domain/daily_rollups.py:281–289`.
   Aggregate identity includes timezone, but selection checks only installation. Two 8,000-step rows for the same installation/date in Los Angeles and New York are both selected; Today reports 16,000. Timezone aliases can produce the same defect without travel. HR summaries choose a timezone variant by ID rather than a declared policy.
   Fix: define one representative aggregate per metric/day/window across timezone variants, retaining provenance and historical rows. Do not simply remove timezone from identity without reconciling day boundaries.
   Validate: aliases, timezone changes/rescans, overlapping windows, different installations, preference changes, Today and analytics.

4. **P1 — Same-instant manual measurements do not win precedence.**
   Files: API `domain/daily_rollups.py:_observation_order`, `summarize_today:292–311`; Today/analytics input projection.
   Representative measurement selection breaks equal timestamps by UUID and has no confirmation/source input. A confirmed manual 70 kg and imported 80 kg at the same instant produced 80 kg in the probe. This violates the plan's explicit precedence rule while retaining both rows.
   Fix: apply manual-confirmed precedence only for comparable metric/instant ties, followed by deterministic tie-breaking; later non-overlapping samples must still win by time.
   Validate: both insertion orders and ID orders, equivalent UTC offsets and units, manual/import ties, and genuinely later imported measurements in Today/trends/context.

5. **P1 — Deletions arriving before creation are forgotten.**
   Files: API `application/healthkit_import_service.py:516–523`; `persistence/models.py:HealthKitImportIdentity`; phase 8 migration.
   An unknown tombstone is acknowledged as unchanged without persisting any deletion identity. A later stale batch/rescan creates the deleted sample. Reproduced: deletion ACK followed by the same sample yielded `created_count=1`. The identity schema requires a canonical object, so it cannot currently represent deletion-before-import.
   Fix: persist an owner/type/source deletion identity even when no object exists; late sample reads must not resurrect it. Preserve owner isolation and avoid fabricated health records.
   Validate: delete-before-create, reordered batches, concurrent installations, repeated tombstones, atomic rollback and erasure cleanup on PostgreSQL.

6. **P1 — Aggregate tombstones permanently suppress legitimate recomputation.**
   Files: API `application/healthkit_import_service.py:438–440,526`; aggregate identity/lifecycle contract.
   Sample UUID tombstone semantics are also applied to reusable device-day keys. After removing the day's aggregate, later valid data for that day is always ignored. Reproduced: 100 steps → tombstone → fresh 200-step summary returned unchanged and Today remained unknown.
   Fix: distinguish terminal sample deletion from a recomputable daily summary. Accept a provably newer aggregate after new day data while rejecting stale resurrection, preserving history and corrections. Define its ordering/lifecycle contract explicitly.
   Validate: empty-day deletion followed by new samples, partial deletion/recompute, stale retry, repeated delete, HR summary equivalents and analytics invalidation.

7. **P2 — User archiving an import can poison future batches.**
   Files: API `application/healthkit_import_service.py:490–530`; `application/daily_service.py:update_daily_item`, `archive_daily_item`.
   User archive leaves device/unconfirmed provenance and no import tombstone. A later native deletion calls archive again and returns 409, rolling back the entire batch; changed source content similarly attempts an illegal archived update. Reproduced archive 200 → native deletion 409. Unrelated valid entries in that batch cannot progress.
   Fix: recognize user-archived imported rows as protected inactive state; process deletion idempotently and define source-update handling without restoring the row or rejecting unrelated changes.
   Validate: user archive followed by changed source, native delete and replay, with another valid item in the same transaction.

8. **P1 — Different batch IDs allow stale aggregates to overwrite newer data.**
   Files: API `domain/healthkit_imports.py:HealthKitImportBatchRequest`; `application/healthkit_import_service.py:486–514`; identity persistence.
   Receipt hashes protect identical batch-ID replay only. For a different ID, any different content wins in arrival order; there is no source revision, generation or comparable observation ordering. Owner locks serialize writes but do not establish freshness. Reproduced newer 200-step summary followed by delayed older 100-step batch: current value reverted to 100.
   Fix: define/enforce bounded ordering or compare-and-swap semantics for aggregate recomputation; reject/ignore stale updates without breaking retry or corrections. Reconcile the plan/contract before changing generated DTOs.
   Validate: reordered distinct batches, retries, simultaneous sync/rescan, tombstone versus update, and cross-installation cases using PostgreSQL concurrency tests.

9. **P2 — Concurrent coordinator calls regress the native anchor.**
   Files: mobile `coordinator.ts:35–62`, `CheckpointStore` contract.
   There is no per-scope exclusion or generation check. A delayed older call saves its anchor after a newer call completes. A deterministic harness using the actual transpiled coordinator ended at `old-anchor` after `new-anchor` was acknowledged and saved.
   Fix: serialize sync work per owner/installation/type/policy, including recovery after acknowledged checkpoint failure; do not compare opaque anchor strings. Keep upload and durable checkpoint ordering coherent.
   Validate: reversed ACK order, delayed/failed storage, duplicate calls, recovery, and independent scopes progressing separately.

10. **P2 — Coordinator consent is detached from the authenticated session.**
    Files: mobile `coordinator.ts:12–44`; `apps/mobile/src/features/healthkit/api.ts`; `apps/mobile/src/auth/authenticatedFetch.ts`; consent/lifecycle integration.
    The coordinator trusts a caller's `ownerId` and stale boolean, while the production API client authenticates the account current when the request starts. Work prepared with A's consent can be submitted after switching to B and be attributed to B; turning the type off after preparation likewise does not stop submission. Root UI remounting does not cancel independently running coordinator work. No native caller exists today, so this is a foundation gate before wiring one.
    Fix: bind prepared sync to the verified session/account generation, recheck type consent before upload, cancel/discard pending work on account changes/disable, and prevent misleading checkpoint saves under an old scope.
    Validate: switch/logout/expiry/disable between preparation and upload, during token acquisition and before ACK/checkpoint; B receives no A data and requires its own consent.

11. **P2 — Source preference hides user-confirmed corrections.**
    Files: API `application/daily_service.py:update_daily_item`; `application/today_service.py:119–128`; `application/analytics_service.py:_load_inputs`; import identity selection.
    Editing an aggregate makes the canonical row manual/user-confirmed, but its import identity remains subject to `analytics_selected`. An unselected aggregate corrected to 300 steps was still absent from Today. Switching preferences can similarly remove an already corrected row from timeline and analytical inputs. Protecting the value from sync overwrite does not preserve its usability as manual state.
    Fix: define manual correction precedence independently of device preference and keep corrections discoverable. Separate timeline visibility from representative analytical selection; avoid introducing duplicate daily totals.
    Validate: correct selected/unselected aggregates, switch preferences afterward, source update/delete, and coherent Today/trends/evidence results.

12. **P2 — AI Today summaries bypass aggregate selection and lose interpretation metadata.**
    Files: API `application/ai_context_service.py:_candidate_branch`, `_today_summaries`; shared selection/rollup boundary.
    Phase 8 filters unselected aggregates in Today and analytics, but not context's Today summaries. After explicitly allowing both installations' observations, the context probe summed 100+200 steps to 300. The context projection also omits HealthKit stage/method/range/coverage metadata, so consented sleep and HR data lose the meaning needed for interpretation. Import defaults remain restrictive; this occurs after legitimate item consent.
    Fix: reuse the canonical representative policy within consented inputs; permission filtering must still precede assembly and must not substitute an unconsented preferred source. Include only required typed/allowlisted interpretation metadata, or exclude representations that cannot yet be interpreted safely.
    Validate: selected/unselected permitted combinations, denied/excluded inputs, manual corrections, preference switches, sleep stages, HR coverage, and context size limits. Provider remains disabled.

13. **P2 — Step counts bypass the established numeric safety bound.**
    Files: API `domain/schemas.py:StepCountValueV1`; `application/daily_service.py:_observation_fields`; `domain/daily_rollups.py`; mobile step edit validation and generated contract.
    The new integer has a lower bound only, unlike other daily numbers bounded at `1e300`. A valid 401-digit integer reaches `float(value.value)` and produces sanitized 500 rather than input rejection. Large finite integers above the domain bound can also be persisted and make summaries exceed safe numeric limits.
    Fix: enforce the established conversion-safe bound before persistence and reflect it in the generated contract/mobile validation; preserve valid explicit zero.
    Validate: zero, boundary, above-bound and float-overflow integers through import and manual create/update APIs; malformed compound saves leave rows, history, sequences and receipts unchanged.

14. **P2 — Import validation accepts incomplete or wrong temporal shapes.**
    Files: API `application/healthkit_import_service.py:_validate_entry`; `domain/schemas.py:ObservationSchemaV1`; mobile `mapping.ts:mapWorkout`.
    Workout imports require an exact start but allow neither end nor duration, despite the normalized retention contract requiring one. Weight/resting-HR imports can carry `interval_end` from the broader manual Observation schema and then participate across multiple days rather than as instant measurements. The globally exposed step type also accepts instant time, despite its declared daily/date-only semantics and mobile editor requirement.
    Fix: enforce import-specific workout and low-frequency point shapes; enforce date-only step semantics in the canonical domain contract. Preserve the broader existing manual workout rules where intentionally supported.
    Validate: missing workout end/duration, unsupported low-frequency intervals, instant steps through manual APIs, valid mapped records, rollback, OpenAPI and generated-client consistency.

15. **P2 — Preference invalidation has a read race.**
    Files: API `api/daily.py:get_today:875–884`; `application/today_service.py:load_today_snapshot`; `application/healthkit_import_service.py:set_healthkit_source_preference`.
    A continuation first checks its snapshot marker, then loads rows using mutable selection flags. A preference transaction committed between those operations deletes the marker but the request still succeeds using the new selection. Deterministic PostgreSQL interleaving reproduced a first page reporting 100 steps and a 200 continuation reporting 200 steps with the old cursor.
    Fix: read/validate selection and snapshot consistently, or detect a preference generation change and reject/restart the page. Use a proportionate transactional/versioning solution rather than assuming marker deletion removes the race.
    Validate: switch preference between cursor validation and row loading and during first-page reads; each page set retains one selection or requires restart, with no missed/duplicated entries.

16. **P2 — The delivered PostgreSQL preference test fails.**
    File: `services/api/tests/test_healthkit_import_api.py:278`.
    It expects 409 for the invalidated Today cursor, but `api/daily.py` deliberately returns 422 `invalid_cursor`, consistent with Today OpenAPI. Running the phase 8 suite with a real database yields six passes and this failure. It was skipped in release evidence.
    Fix: reconcile the assertion with the intended public cursor contract (422 is current behavior); assert the error code and verify refreshed paging/source selection. If deliberately changing the API instead, update contract/client/docs together. Do not claim database acceptance while this fails.
    Validate: run the complete phase 8 PostgreSQL suite plus the race test above.

Validation performed: 22/22 focused mobile tests passed; phase 8 Python tests on fresh temporary PostgreSQL: 6 passed, 1 failed; related daily/domain/persistence/analytics/context suites: 48 passed, 3 failed. Those three failures also reproduce on the parent commit using a separate fresh database: `test_conversion_bound_is_a_sanitized_input_error_before_persistence`, `test_context_and_search_follow_daily_permission_revisions`, and `test_today_summary_keeps_symptom_severity_linked_within_included_scope`. Treat them as existing baseline failures, not phase 8 regressions. Fresh migration upgrade succeeded, and runtime OpenAPI equals the checked-in artifact. Synthetic API probes confirmed findings 2–8, 11–13 and 15; installed library/source and a deterministic coordinator harness establish 1 and 9. Findings 10 and 14 are explicit contract/lifecycle gaps from source inspection, not claims of observed native behavior.

For follow-up: keep fixes focused on these findings; add meaningful regression coverage and rerun affected integrations. Preserve thin routes, owner-scoped transactions/history, manual correction protection, restrictive AI defaults, private storage and the mobile-only native boundary. Reconcile changed lifecycle/ordering/selection decisions in the plan/contract before implementation. Record PostgreSQL evidence separately from native/device acceptance; do not enable any unverified HealthKit type.
