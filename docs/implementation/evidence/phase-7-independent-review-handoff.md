# Phase 7 independent review — handoff for Luna XHigh

Reviewed October 7, 2026: commit `7c3925f` against parent `af87d3e`.
This implementation is **not sound yet**. The first finding blocks persisted
analytics at runtime; the other findings remain relevant after that blocker is
fixed. No substantive fixes were made during this review.

For the fresh **Luna XHigh** session: start with `docs/README.md` and
`docs/current-state.md`, then the Phase 7 plan/release record and this handoff.
Treat this as the review backlog, not authorization for unrelated phase work.
P1 means fix before Phase 7 acceptance; P2 means a concrete correctness or
completeness issue to resolve in this phase. Findings below are not capped.

Review covered the commit diff, numerical/domain contracts, application and API
paths, migration/models, daily/proposal integration, AI context permissions,
generated contracts, mobile Insights/Today and existing tests. It also compared
the product/UX intent, security baseline, canonical-state/JSONB/tracker ADRs and
the written plan. The reconciled numeric-only tracker scope, disabled provider,
and logging-only recommendation without a proposal are reasonable documented
scope decisions; they are not findings.

## Actionable findings

1. **P1 — Every analytics revision snapshot is not JSON serializable.**
   **Files:** `services/api/src/health_api/application/analytics_service.py:144`
   (`_snapshot`, `_append_revision`); persistence JSONB serialization.
   Snapshots contain UUIDs (`object_id`, `source_id`) and raw datetimes. The
   configured SQLAlchemy engine uses ordinary JSON serialization, unlike the
   existing daily/profile snapshot builders that stringify these values.
   `json.dumps(_snapshot(...))` reproduces `TypeError: Object of type UUID is
not JSON serializable`. Flushing history therefore fails for new signals,
   experiments, insights/recommendations and subsequent state revisions. The
   SQLAlchemy error handler turns the failure into 503 and the transaction rolls
   back. **Fix:** produce a validated JSON-safe snapshot consistent with the
   canonical history conventions. **Validate:** real PostgreSQL creation,
   update, invalidation, expiry and lifecycle writes, including history
   round-trip and rollback; a JSON serialization regression test alone is not
   database acceptance.

2. **P1 — AI trend context ignores explicit object exclusions.**
   **Files:** `application/ai_context_service.py:591`,
   `application/analytics_service.py:1043` and `_load_inputs`.
   Entry selection honors `excluded_object_ids`, but the independent trend
   query receives none of them. An explicitly excluded opted-in measurement or
   tracker entry still contributes to numbers and appears by ID/revision in
   trend evidence. Excluding the tracker definition also does not prevent its
   summary. This violates purpose-scoped user control even while the provider
   is disabled. **Fix:** apply request exclusions throughout trend loading,
   tracker authorization and relationship eligibility, before aggregation.
   **Validate:** exclude the sole input and then one of several inputs; verify
   values, coverage and evidence omit it. Cover excluded tracker definitions,
   linked symptom endpoints, and continued denial of unconsented/foreign data.

3. **P2 — AI trends violate the context's `as_of` boundary.**
   **Files:** same AI context/analytics paths, especially `_load_inputs`.
   Context entries restrict instants to before `as_of` and check envelope
   validity. Trends use the end of the selected calendar date and only check
   active status/AI permission. A later measurement on that date can therefore
   appear in a context preview requested for an earlier instant. Interval
   contributions can also extend beyond the requested instant.
   **Fix:** carry the context time/validity policy into analytics candidate
   selection and define interval clipping consistently with that policy.
   **Validate:** before/after-`as_of` inputs on the same date, crossing intervals,
   validity bounds, date-only semantics and timezone/DST cases.

4. **P1 — Symptom severity drops the very observations it must analyze.**
   **Files:** `application/analytics_service.py:752` (`_standard_points`);
   `application/today_service.py` (`summarize_today_snapshot`).
   The filter keeps severity observations whose IDs are _not_ linked, reversing
   Today's eligibility rule. Ordinary daily saves require severity to be linked
   to a symptom Event, so valid severity trends become null; associated insights
   and experiment outcomes become unavailable. A synthetic episode with linked
   severity 4 reproduced null, known_count 0, partial true. **Fix:** use active,
   same-day eligible symptom endpoints and their severity observations, with
   consent-safe relationship handling for AI previews. **Validate:** Today/trend
   parity, multiple episodes and latest selection, unrated episodes, explicit
   severity zero, archived/out-of-window parents and independently withheld
   endpoint permissions.

5. **P1 — Updates that introduce a new input leave affected analytics current.**
   **Files:** `application/analytics_service.py:293` (`_invalidate_referenced`);
   `application/daily_service.py:979`.
   Update invalidation follows only existing evidence edges. Move an existing
   row from outside a saved window into it, change a measurement to that
   window's metric, or move a tracker entry into its outcome scope: the old
   result has no edge to that row, so its insight/recommendation remains current
   despite changed inputs. New-row invalidation handles this case, edits do
   not. **Fix:** invalidate both scopes losing input and scopes gaining input;
   a conservative owner-wide fallback for such updates is acceptable.
   **Validate:** date/interval/domain/metric/tracker-field changes into and out
   of saved scopes, sparse/empty results, same-transaction rollback, and future
   import use of the hook.

6. **P1 — Optimistic concurrency checks can read stale ORM instances.**
   **Files:** `application/analytics_service.py:1611` (`_update_artifact`),
   `:1944` (`expire_artifact_for_response`), persistence session factory.
   These paths first load aggregates, commit, then reselect under locks.
   Sessions use `expire_on_commit=False`; reselecting a mapped object or using
   `session.get` does not refresh a retained identity-map instance. A concurrent
   state/revision change can therefore evade the expected-revision check or
   lifecycle check. The revision uniqueness constraint can then produce 503
   instead of the promised 409. The same pattern can fail expiry reads.
   A minimal SQLAlchemy reproduction returned cached revision 1 after a
   locked reselect while a scalar query returned actual revision 2.
   **Fix:** refresh/populate current envelope and artifact state under the
   appropriate locks, and check revision, lifecycle and expiry there.
   **Validate:** coordinated two-session PostgreSQL edit/start/stop,
   accept/dismiss/invalidate and expiry races; exactly one valid writer, intact
   history and deterministic conflicts rather than storage errors.

7. **P2 — Reviving deduplicated artifacts reuses obsolete evidence and decisions.**
   **Files:** `application/analytics_service.py:871`, `:1203`, `:1307`, `:1399`.
   An unrelated new daily row stales all analytics. Recomputing an unchanged
   scope revives the same signal ID at a new revision. Insight/recommendation
   dedupe keys use only its ID; `_persist_object_artifact` validates newly
   constructed references but returns the old payload/evidence, changing only
   state. The revived item still references the prior signal revision. An
   accepted recommendation can also become proposed again through
   accepted → stale → proposed, despite identical evidence/results.
   **Fix:** define reactivation explicitly: retain historical snapshots and
   user decisions, and ensure a newly current artifact has the intended exact
   signal revision/evidence. Use revisions/new artifacts as needed rather than
   rewriting historical meaning. **Validate:** unrelated insert followed by
   unchanged recompute, repeated revival, accepted/dismissed histories, exact
   evidence resolution and idempotency.

8. **P2 — State-filtered lists paginate before accounting for expiry.**
   **Files:** `application/analytics_service.py:1571`;
   `api/analytics.py` (`_list_artifacts`, response conversion).
   `state=current` or `proposed` selects persisted state first; response
   conversion then expires rows. A current query can return expired items,
   while an expired query omits expired-by-time rows until another read touches
   them. Expired rows consume page limits and Today can show no cards despite
   valid current insights farther down the list. **Fix:** filter effective state
   including expiry before limiting/cursor construction, with consistent read
   semantics. **Validate:** mixed expired/current pages, expired queries before
   any detail read, cursor traversal and Today's three-card limit.

9. **P2 — Explicit refresh cannot renew an expired unchanged result.**
   **Files:** `application/analytics_service.py:1203`, insight/recommendation
   dedupe construction.
   Refreshing the same historical window/input after seven days returns its
   expired artifact forever: dedupe finds the same signal-ID key, and expired
   objects are neither renewed nor replaced. A fresh evidence review cannot
   create a current result unless source data or scope changes. **Fix:** provide
   explicit renewal semantics with retained expired history, refreshed validity
   and exact evidence, while preserving dismissal decisions and idempotent
   repeats within one validity period. **Validate:** controlled-clock refresh
   before/after expiry, concurrent renewals, unchanged numbers and history.

10. **P2 — Legal tracker names/labels break the entire metric catalog.**
    **Files:** `domain/analytics.py` (`MetricDefinition.label`);
    `application/analytics_service.py:546`, `:597`.
    Tracker names and field labels each allow 120 characters, but their composed
    analytics label is limited to 80. A valid 60-character name plus
    30-character field label produced a 105-character label and Pydantic
    `string_too_long`. One such tracker makes `/analytics/catalog` fail with 500;
    the mobile `Promise.all` then prevents the entire Insights screen loading.
    **Fix:** reconcile display bounds or deterministically shorten the label
    without losing metric identity/version. **Validate:** maximum legal names,
    Unicode, multiple fields/versions and successful catalog/trend/experiment
    operations. Regenerate contracts if bounds change.

11. **P2 — Stopping/completing an experiment does not bound its observed period.**
    **Files:** `domain/analytics.py` (`ExperimentPayloadV1`);
    `application/analytics_service.py:1855`, `:1885`.
    Lifecycle transitions only change status. Results always include all data
    through the originally planned `end_date`, even after an early manual stop
    or completion, and there is no actual termination boundary. Subsequent
    ordinary logs are presented as intervention observations after the user
    stopped the intervention. **Fix:** preserve planned design separately from
    the actual lifecycle boundary; truncate the observed comparison or clearly
    represent a planned-window summary that cannot imply continued intervention.
    **Validate:** early stop/completion, subsequent logs, empty/truncated periods,
    future planned dates, timezone rules and immutable history.

12. **P2 — Evidence drill-down uses the wrong resource and revision.**
    **Files:** `apps/mobile/src/features/insights/screens/InsightsScreen.tsx:530`
    and insight evidence rendering; daily item/history screens.
    Links pass only `itemId`. DailyItemScreen defaults missing `type` to event,
    so observation links call the Event endpoint and fail. Links also display
    an exact revision label but open the current object rather than that
    retained revision. Derived-signal links are disabled; only eight references
    are accessible with no expansion. A stale insight cannot be audited as
    promised. **Fix:** route by type and resolve the referenced historical
    revision, expose the linked signal's original window/method/results and
    make the remaining evidence reachable. **Validate:** Event/Observation,
    edited/archived sources, old signal revisions, foreign IDs and more than
    eight references. Keep current edits clearly distinct from evidence views.

13. **P2 — Mobile keeps obsolete analyses and current cards after data changes.**
    **Files:** `InsightsScreen.tsx` focus loading, `generateInsights`, cached
    `trend`, `associations`, `results`.
    Focus reloads lists but retains computed results. Navigate to a daily edit
    and back: old numbers remain displayed without stale/recompute status.
    Refresh merges generated IDs into existing insight/recommendation arrays,
    so different-fingerprint predecessors invalidated on the server can remain
    locally marked current/proposed. **Fix:** invalidate/revalidate cached
    analyses on focus/source changes and refresh authoritative artifact states
    after computation; label any intentionally retained snapshot. **Validate:**
    edit/archive/insert-return flows, regeneration with new signal IDs,
    experiment result caching, request failures and screen navigation races.

14. **P2 — Experiment form can silently save a different outcome than shown.**
    **Files:** `InsightsScreen.tsx` (`editExperiment`, metric selector,
    experiment outcome label).
    Editing loads `form.outcome_metric` but leaves the analysis selector
    `metric` unchanged. The form label uses the latter's `selectedMetric`, so a
    weight experiment can visibly say sleep while saving weight. Conversely,
    choosing an analysis metric also mutates an open experiment draft.
    **Fix:** bind the outcome selector/label to the experiment form, separate
    analysis selection, and preserve explicit primary-outcome choices.
    **Validate:** edit a draft whose outcome differs from the analysis metric,
    switch metrics, cancel/retry and confirm the submitted outcome matches the
    displayed label/unit/version.

15. **P2 — Notes cannot be edited after an experiment starts in mobile.**
    **Files:** `InsightsScreen.tsx` experiment edit action/form.
    The service intentionally allows notes edits after start, but mobile only
    exposes `Edit draft` for draft status. Users cannot record progress or
    stopping/completion notes in active/completed/stopped experiments.
    **Fix:** expose notes-only editing for supported post-start states, keeping
    design fields read-only and using expected revisions. **Validate:** notes
    revisions in each lifecycle, immutable design, archived restrictions and
    stale-save conflicts.

16. **P2 — Mobile silently truncates all saved history at 50 items.**
    **Files:** `InsightsScreen.tsx` initial list loading.
    Insight, recommendation and experiment calls ignore `next_cursor`. Older
    artifacts, including an older active experiment, become unreachable once
    enough newer objects exist. **Fix:** add bounded load-more/state filtering
    or another reachable paginated history surface, without fetching unlimited
    histories at once. **Validate:** more than 50 items per type, stable cursor
    traversal, older active/draft experiments and no duplicated/skipped cards.

17. **P2 — Experiment planning-reference checks are not protected at commit.**
    **Files:** `application/analytics_service.py:1725`, `:1746`, `:1772`,
    `:1817`; planning update/archive integration.
    Create/draft edit validate references before the commit that starts the
    write transaction. Start revalidates inside its transaction, but does not
    lock/refresh the planning target or tracker. Planning writes lock their own
    objects and do not share the analytics owner lock. A referenced resource
    can change/archive between validation and experiment commit, permitting an
    experiment start against an already invalid resource.
    **Fix:** validate current owner/type/revision/lifecycle in the write
    transaction with appropriate resource locks and a consistent lock order.
    **Validate:** two-session draft create/edit/start versus target edit/archive
    and tracker lifecycle changes; reject invalid starts and avoid deadlocks.

18. **P1 — The required Phase 7 executable verification was never delivered.**
    **Files/components:** `services/api/tests`, `apps/mobile/tests`,
    migration verification, Phase 7 plan/release evidence.
    The commit adds no tests despite the plan's numerical goldens, revision/race,
    permission, experiment and UI requirements. Existing suites do not exercise
    analytics, which is why a fundamental serialization failure passed static
    verification. **Fix:** add focused tests alongside the fixes plus remaining
    phase acceptance coverage; do not mark Phase 7 accepted from compilation.
    **Validate:** hand-calculated trend/Spearman fixtures (ties, constants,
    contradictory/sparse data, zeros, outliers), unit/DST/schema-version parity,
    bounds/error/foreign-owner cases, persistence/evidence/idempotency,
    lifecycle/expiry/concurrency, AI restrictions and mobile flows above. Run
    disposable PostgreSQL migration/drift checks and representative query/CPU
    measurements. `_standard_points` recomputes all daily rollups per metric
    per day; measure maximum supported requests before claiming performance,
    without introducing speculative infrastructure. Record device accessibility
    and timezone walkthroughs separately from automated proof.

## Verification and limits

- API suite: `135 passed, 50 skipped`; PostgreSQL tests skipped without
  `TEST_DATABASE_URL`. No live database/provider/cloud/device claim is made.
- Existing mobile Vitest suite: `21 files, 98 tests passed`. Mobile TypeScript
  check passed. Used the already-installed Node runtime directly because the
  default pnpm was version 11, outside the repository's pinned version 9 range.
- Runtime OpenAPI exactly matches checked-in JSON. Generated client schemas
  and analytics transport methods were inspected; mobile typecheck passed.
- `git diff --check` passed before this handoff was added.
- Temporary, synthetic, non-persisted probes reproduced snapshot serialization,
  linked severity loss, valid-tracker label failure and SQLAlchemy stale
  identity-map behavior. The latter demonstrates ORM semantics, not a live
  PostgreSQL race. No production source or tests were modified.

Resolve the persistence blocker first, then permission/numerical/state issues.
Reconcile behavior changes with the plan/contracts and update release evidence
to distinguish passing checks from still-open acceptance gates. No new provider,
queue, database or Phase 8 work is needed to address these findings.

## Implementation response — October 7, 2026

The follow-up changes address the corrective code requests above. Snapshots
are JSON-safe; AI previews apply exclusions, tracker consent, envelope validity,
`as_of` filtering, and interval clipping; symptom severity uses same-day linked
severity observations; daily edits invalidate owner-wide; and locked analytics
reads refresh ORM state. Insight/recommendation identity includes exact signal
revisions, decisions persist across stale/recomputed history, expired undecided
artifacts can renew with a retained revision, and list state filtering accounts
for expiry before pagination. Tracker labels are bounded without changing
metric IDs. Experiment results stop at the recorded terminal time, while
planning and experiment writes use owner-first locking. Mobile now resolves
exact evidence revisions, reloads effective state, protects focus-scoped
analysis requests, separates experiment outcomes from analysis selection,
allows notes-only edits after start, and pages older artifacts.

Focused regression tests now cover JSON serialization, linked symptom severity
including zero/latest/cross-day cases, tracker label bounds, terminal experiment
timestamps, trend coverage/rolling means/calendar-half comparisons, zero
baselines, tied/constant/inverse Spearman values, and association thresholds.

Follow-up checks passed: API suite `144 passed, 50 skipped`; mobile suite
`21 files, 98 tests passed`; mobile TypeScript and changed-file ESLint; Mypy for
all 38 API source files; Ruff check/format for changed Python files; OpenAPI
consistency check; and generated-client regeneration. The skipped database
tests require the disposable PostgreSQL environment. No live database,
migration, or concurrency claim is made.

Finding 18's full acceptance matrix remains open: additional numerical,
unit/DST, schema-version, ownership, persistence, lifecycle, AI permission and
`as_of` integration coverage; coordinated PostgreSQL races and migration/drift
checks; query-plan measurements; analytics-specific mobile interaction tests;
and device walkthroughs. Phase 7 remains unaccepted until those gates are
completed and separately evidenced.
