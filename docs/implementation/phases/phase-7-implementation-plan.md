# Phase 7 — Evidence-linked insights, recommendations and experiments

## Implementation-time reconciliation gate

Check [current state](../../current-state.md) for delivery status and open gates. This plan defines intended scope; it is not evidence of delivery or authorization to begin work. Before implementation or a follow-up, inspect current code, preceding release/review evidence, accepted ADRs and contracts, and external dependencies. Reconcile material drift here before coding.

## Goal / scope

**Deliver:** deterministic derived signals/trends and modest association analysis first; evidence-linked insight/recommendation objects with uncertainty/expiry; transparent Insights surface and manual experiments. Optional AI explains supported results through Personal AI, without becoming numerical/domain authority.

**Defer:** medical diagnosis, causal claims, automated prescription/dose changes, advanced N-of-1 statistics, arbitrary semantic/vector pipelines, wholesale background recomputation, native/record inputs until Phases 8–9, web. Sparse manual data may produce no insight; that is a valid useful result rather than manufactured certainty.

## Deterministic analysis contract

Reuse Phase 2 metric catalog and Phase 4 explicit numerical tracker field semantics. Define a supported catalog in code/docs: daily known nutrition energy subtotal (partial intake), logged exercise/sleep duration, symptom-severity summaries and latest weight/pulse/other supported measurement series. Numerical analysis only for comparable metric/unit/schema versions. Boolean/enum tracker rates require explicit known denominator; missing entries are excluded and unknown count disclosed. Do not mix symptom absence with severity0, or interpreted completed intent with actual activity.

A planned `derived_signals` subtype uses envelope owner/lifecycle/provenance plus signal kind, metric(s), window, timezone, method_version, parameters, result, coverage and evidence revision references. Origin system-computed + `unconfirmed` confirmation status and derived analytical lifecycle; never a Profile fact. Computation key `(owner,method_version,metric,window,parameters,input_fingerprint)` makes recompute idempotent. Unit conversion/overlap/day rules reuse Phase 2. Start on-demand bounded queries (max366 days/max10K input rows; page/downsample for display with explicit method), not jobs/bus. If bounds exceeded return a specific “range too large” result and narrow query; don't drop arbitrary rows silently.

Trend v1: known daily points, counts/coverage, median/mean where metric appropriate, optional rolling7-known-day mean labeled with known count, no zero-filled gaps/interpolation. A period comparison requires ≥5 known days in each comparable period; no percentage change against zero or incomparable units. Label numerical change as descriptive, not clinically meaningful. Sleep/exercise duration aggregation and nutrition completeness remain explicit. For latest-only measurements, daily representative selection is deterministic and method-versioned.

Association v1: pair known day-level values with explicit same-day lag0 or predefined lag1, require ≥14 paired days across ≥21 calendar days, exclude constant/non-finite series and report `insufficient_data`/`constant_series`; compute Spearman rank correlation with deterministic tie handling. At most5 predefined metric pairs per query; no all-pairs fishing. Show paired count, date window, missing count, effect/rank statistic and “association only; confounding and reporting bias possible.” No statistical significance/causal label unless separately justified methodology is added. Thresholds are conservative product/display gates, not clinical validation. Stable numerical fixtures should include contradictory/sparse examples, tie/constant/outlier/zero cases; actual implementation must document algorithm precision/tolerance.

Input edits/archive/import adjustments invalidate dependent signals via revision fingerprints. Preserve prior signal/insight snapshot for audit and mark stale; only current complete recompute can replace it. Evidence identifies exact owner object+revision and derived method/window; current row drifting must not rewrite what an old insight said. Permission review happens when constructing AI context, not merely when signal was created; derived eligibility is no less restrictive than input permissions.

## Insight, recommendation and experiment contracts

Planned `insights`: title, bounded explanation, kind trend/association/coverage, evidence refs/signal IDs, uncertainty/limitations, generated method/source, valid/expiry times and state current/stale/dismissed/expired. Deterministic templates can produce initial insight text; optional Personal AI explanation must not change statistics or invent evidence. Create only when catalog rules pass; insufficient data yields transparent trend UI without a fake insight card. Evidence must resolve to owner-authorized retained revisions. Expiry default7days, at most30days; evidence edit or context change may mark stale sooner.

Planned `recommendations`: owner-visible suggestion, rationale/evidence, risk class, expected review context, expiry (default7days/max30days), state proposed/accepted/dismissed/expired/stale and optional proposal reference. “Accepted” records interest, not canonical plan/goal creation. Actionable recommendation creates a Phase 6 pending typed proposal only for supported command kinds; user still reviews and confirms. Already-expired/stale recommendation cannot spawn a proposal without renewed evidence review. No medication dosage proposal or ungrounded diagnosis. AI-authored recommendation provenance stays AI-derived, never confirmed fact. Generated analysis artifacts are Health-owned, schema-validated unconfirmed outputs of bounded analysis requests, not a generic Personal AI write capability. Model text cannot mutate Profile, daily logs, plans or experiments; those effects still require supported Phase 6 proposals and user confirmation. Manual dismissal history and source snapshots preserved.

Planned `experiments`: hypothesis in user words, intervention description, linked owner goal/plan/tracker, chosen outcome metric, baseline/start/end dates, status draft/active/completed/stopped/archived and user-stated notes; bounded immutable revisions. One explicit primary outcome avoids retroactive cherry-picking. No blinded/randomized protocol or medical intervention engine; UI warns about limitations using approved content. Start validates dates/metric/version and available logging; outcomes reuse deterministic series/coverage and report descriptive baseline/intervention comparisons, not causal proof. Starting/stopping is manual; AI can discuss but not autonomously modify experiments. Do not add new experiment proposal command casually; unsupported suggestions remain prose/manual forms.

Persist signals/insights/recommendations/experiments only when needed for history/evidence and user review, reusing canonical source/history machinery rather than a second analytics authority. Owner-specific inputs and links must be rechecked, including generated aggregate references.

## API / UX / AI extensions

Planned read routes `GET /trends?metric=...&from=...&to=...&timezone=...` and bounded `/associations` return values plus method/coverage/evidence or explicit unavailable reason. `/insights` and `/recommendations` list/detail/state-action routes; recommendation proposal creation calls the existing executor boundary, never direct domain writes. `/experiments` manual CRUD/lifecycle plus `/experiments/{id}/results` uses catalog rules. Existing pagination50/max100, expected revisions, create UUIDs, foreign404, conflict409, malformed422, dependency503 conventions apply. Deterministic compute requests must not grant cross-owner query access. Rate/size bounds protect expensive queries; clear 422 for unsupported/range-limit, 429 for abusive request limits if needed.

Context Pack/search extend with permitted current trends/insights/recommendations/experiment summaries; register narrow `health.trends` read capability through actual Phase 5 protocol and version contracts. Derived permissions propagate from inputs. Personal AI continues to orchestrate models/research; Health computes statistics and verifies references. No provider call required to display trends/insights or manually manage experiments.

Mobile `src/features/insights` displays trends with gaps/coverage, association limitations, insight evidence drill-down, recommendations/expiry/history and manual experiment forms/results. Today adds bounded relevant current cards without changing daily summaries. Chart/table accessibility, text alternative and unit/window labels; insufficient/loading/empty/expired/stale/unsupported/disabled AI/error/offline states. Proposal confirmation UI is reused from Phase 6. Don't make a chart look complete when samples are sparse.

## Analytical execution order / work packages

`P7.1 catalog & fixtures -> P7.2 deterministic signals -> P7.3 evidence objects/API -> P7.4 experiments -> P7.5 UX/AI explanation -> P7.6 audit`. Experiments can start after numerical contracts; explanations cannot precede validated statistics/evidence.

### P7.1 — Freeze metric/coverage/method catalog

**Dependencies:** reconciliation. **Goal:** auditable numeric semantics.

**Areas:** domain/application analytics modules (provisional), data/API docs and tests/fixtures.

**Work:** explicit catalog, aggregation/units/time/thresholds/precision and analysis bounds; construct sparse/no-signal/association/confounding fixtures.

**Requirements:** no absence-as-zero, no inferred regimen adherence or causal language. **Tests:** hand-computed goldens, conversions/DST/ties/constants/non-finite and incomparable tracker versions. **Acceptance:** expected outputs/limitations approved before UI. **Out of scope:** ML models/advanced inference.

### P7.2 — Build deterministic queries and derived signals

**Dependencies:** P7.1. **Goal:** stable results tied to exact inputs.

**Areas:** application/persistence/migrations/API tests; provisional signal computation/cache-key services.

**Work:** bounded input queries, trend/association methods, evidence snapshots/input fingerprint, stale/recompute behavior; index/profile representative ranges.

**Requirements:** idempotent compute, atomic snapshot identity, owner/permission propagation. **Tests:** repeat computation/revision changes/archive invalidation/races, golden numeric tolerance, input limit and query-plan checks. **Acceptance:** server output matches goldens independent of AI. **Out of scope:** cron/bus/distributed cache.

### P7.3 — Persist explainable insights and recommendations

**Dependencies:** P7.2 and Phase 6 executor. **Goal:** reviewable analytical objects.

**Areas:** domain/persistence/application/API/contracts/client; provisional insight/recommendation schemas/routes.

**Work:** additive subtypes, evidence/expiry/state actions, deterministic initial templates, recommendation→pending proposal linkage and stale validation.

**Requirements:** acceptance ≠ application; exact revisions and risk floor; no unsupported commands. **Tests:** foreign evidence/expiry/stale source, duplicate recommendation/proposal creation and user-only apply, AI explanation inventing reference/statistic. **Acceptance:** insight/recommendation audit chain resolvable and no auto health writes. **Out of scope:** diagnostic recommendations/dosage plans.

### P7.4 — Manual experiment lifecycle and descriptive results

**Dependencies:** P7.2/P7.3 data contracts. **Goal:** explicit user-led observation.

**Areas:** provisional experiment subtype/services/routes, tracker/plan links, tests.

**Work:** hypothesis/outcome/date/status contracts, version-preserving manual lifecycle, bounded baseline/intervention queries and coverage-aware descriptive results.

**Requirements:** no automatic causal conclusion, no hidden outcome changes, all refs owner scoped. **Tests:** dates/metric mismatch/empty baseline/missing entries/stopped experiment, concurrent edit and invalid lifecycle. **Acceptance:** results show what is known and why insufficient when appropriate. **Out of scope:** randomization/adaptive interventions/experiment proposal command.

### P7.5 — Insights UX and optional explanations

**Dependencies:** P7.3/P7.4 generated DTOs; Phase 5 adapter for optional explanations. **Goal:** transparent interpretation and action review.

**Areas:** mobile Insights/Today/Assistant/proposal features/tests; context/search capability extension.

**Work:** accessible graphs/tables/evidence/expiry and experiment forms; permitted context sections/read tool; optional provider explanation constrained to validated numbers/evidence.

**Requirements:** useful offline-AI/disabled mode, reused proposal review, visible correlation limitation. **Tests:** sparse/stale/expired/chart accessibility/loading/error, recommendation→confirmation single apply, permission filtering of derived context. **Acceptance:** actual mobile walkthrough shows numerical/evidence truth clearly. **Out of scope:** separate AI orchestration or native inputs.

### P7.6 — Evaluate correctness and hand off import readiness

**Dependencies:** all packages. **Goal:** prevent misleading/inconsistent signals.

**Areas:** evaluations/integration/security/performance docs; provisional phase-7 evidence.

**Work:** full deterministic fixtures, manual/AI interpretation review, bounded-query performance and privacy audit; define recomputation entry points for future imported data.

**Requirements:** mocks not clinical validation. **Tests:** local/staging sparse multi-domain scenario, revision invalidation, proposal/manual regressions, optional actual AI numbers/reference check. **Acceptance:** evidence distinguishes numeric proof from provider/safety review. **Out of scope:** broad claims about efficacy.

## Migration, failure and verification matrix

Additive subtypes/method versions; retain previous result/evidence decoder and never rewrite historical explanation on recompute. Changing algorithm increments method_version and recalculates prospectively, leaving audit. Failed compute returns unavailable without creating partial insight. Disabling AI leaves deterministic analysis and prior insight review available. Rollback old service must support existing analytical payloads or disable new routes; do not drop evidence/recommendation histories. Expiry is enforced at query/action time without a required worker.

| Risk                        | Deterministic offline/DB evidence                           | External/manual                                |
| --------------------------- | ----------------------------------------------------------- | ---------------------------------------------- |
| Numerical accuracy/sparsity | Hand-calculated goldens, missing/constant/unit/DST fixtures | Content review; no clinical validation claim   |
| Evidence/invalidation       | Revision/owner/permissions/expiry/race tests                | Real evidence drill-down UX                    |
| Recommendations             | No-write-before-confirmation and stale-link tests           | High-risk policy/provider wording verification |
| Experiment conclusions      | Sparse/descriptive baseline fixtures                        | User comprehension/accessibility               |
| Cost/performance            | Fixed dataset query plans/time/bounds                       | Staging/mobile representative latency          |

## Phase acceptance / completion questions / evidence

Accept when deterministic trends/associations are correct, insufficient data produces honest states, insights/recommendations reference exact evidence and expire, actions use Phase 6 confirmation, and experiments remain descriptive/manual. No HealthKit/record/web work.

Before Phase 8: Can every displayed number be traced to method/input revisions? Are missingness and causal limits visible? Are stale values invalidated on edit/import? Are recommendation actions safe/idempotent? Is AI unnecessary for authoritative computation?

The implementing session must create planned `docs/implementation/evidence/phase-7-release.md`: metric/method versions/thresholds/fixtures, migration head/routes, evidence/stale/expiry/recompute rules, recommendation proposal contract, experiment lifecycle, generated procedure, deterministic/performance/mobile tests, optional live AI/safety review and unresolved checks. Include ingestion invalidation hooks Phase 8 must invoke.
