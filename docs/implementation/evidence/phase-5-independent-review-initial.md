# Phase 5 independent review — initial findings (October 5, 2026)

Reviewed October 5, 2026. Scope: `1c82bd6` through `ddb6f58` inclusive,
diff against `b09f031`, the reconciled phase 5 plan and release evidence,
product/UX/architecture/privacy intent, API/application/domain/persistence,
mobile consent and Assistant flows, migration, generated contracts, and tests.
No substantive fixes were made.

**Assessment: local implementation needs corrections before acceptance.**
Owner predicates, restrictive permission defaults, revisioned daily consent,
bounded packs, parameterized retrieval, and the disabled provider factory are
appropriate. Keeping live integration disabled without a supplied contract is
correct. There is no evidence here of an active provider data leak or AI write
capability. The following are concrete defects or missing requirements, not a
cleanup list. P2 = normal-priority correctness/requirement work; P3 = smaller
robustness or transparency issue. No confirmed P0/P1 defect was found.

## Findings

1. **P2 — The existing mobile test suite regresses.**
   `apps/mobile/src/features/daily/components/DailyEntryForm.tsx:782` and
   `apps/mobile/tests/daily-form.render.test.tsx`.
   All seven daily form render tests fail because the React Native mock lacks
   the newly imported `Switch`. This prevents the existing regression gate
   from passing; it does not establish a native runtime failure.
   **Fix:** update the mock and exercise the consent control, including its
   default and accessibility props.
   **Validate:** the complete mobile suite, consent off/on, edit hydration,
   and compound symptom/blood-pressure request flags.

2. **P2 — Phase 5 has no executable acceptance coverage.**
   `services/api/tests`, `apps/mobile/tests`, and
   `docs/implementation/evidence/phase-5-release.md`.
   Neither implementation commit adds tests. Existing passing tests do not
   prove the new privacy, retrieval, budget, cursor, or Assistant boundaries;
   P5.1–P5.5 explicitly require these, even with a disabled provider.
   **Fix:** add focused phase 5 tests and record actual results. Keep external
   smoke tests distinct from local acceptance.
   **Validate:** PostgreSQL two-owner isolation, opt-out/revocation, archived
   and expired rows, relationship filtering, deterministic ranking,
   mandatory-constraint overflow, final UTF-8 byte budgets, sparse/DST packs,
   FTS paging, daily permission revisions and legacy retries; fake-adapter
   disabled/error/evidence/read-only checks; mobile scope, permission-return,
   offline, draft, and account-switch behavior. Apply/downgrade/re-upgrade the
   additive migration, check model drift, and inspect actual query plans.

3. **P2 — Retrieval ignores planning payload validity dates.**
   `services/api/src/health_api/application/ai_context_service.py:92,127`.
   Planning eligibility checks only envelope validity and `lifecycle=active`.
   Ordinary planning creation leaves envelope validity unset; actual context
   dates live in `start_at/end_at`, and plan/regimen dates in
   `start_date/end_date`. Consequently a future illness context or expired
   regimen remains eligible in both preview and search, and is described as
   current. Phase 4's Today reader already honors these dates.
   **Fix:** apply canonical payload date rules using the selected local date,
   including half-open context endings and inclusive plan/regimen endings.
   Respect goal start dates; reconcile target dates as deadlines rather than
   automatically treating them as expiry.
   **Validate:** before/on/after each boundary, unset envelope validity,
   lifecycle changes, explicit `as_of`, and timezone-adjacent dates in context
   and search.

4. **P2 — AI symptom summaries bypass canonical relationship semantics.**
   `services/api/src/health_api/application/ai_context_service.py:365` versus
   `application/today_service.py:summarize_today_snapshot`.
   The AI builder sends every included severity observation directly to
   `summarize_today`, whereas canonical Today includes severity only when
   linked to an eligible symptom event. A probe with one severity observation
   and no included event returns value `7`, coverage `1/0`, and method
   `latest-linked-episode-v2`. Opt-out, type scope, and truncation make this a
   normal reachable case, even for originally linked observations.
   **Fix:** share the canonical linkage-aware summary logic while restricting
   both sides of each relationship to included, permitted entries. Do not
   infer a withheld event or mislabel an unlinked value.
   **Validate:** unlinked severity, either endpoint opted out/excluded,
   observations-only scope, archived/moved endpoints, budget truncation,
   latest linked severity, and parity with canonical Today for equal inputs.

5. **P2 — Search matches relationship data that context/excerpts suppress.**
   `services/api/src/health_api/application/ai_context_service.py:69,129,504`
   and `migrations/versions/f5c0a1e2d3b4_add_ai_full_text_indexes.py`.
   FTS uses the entire raw JSON payload. An opted-in plan can therefore match
   a reference UUID or referenced item's label even when its target is opted
   out, archived, or outside scope. Context removes such plan items, and
   `_nested_text` suppresses them from excerpts, but neither prevents the
   result-presence signal. Context relationships are likewise searchable by
   withheld IDs/metadata. This violates the planned relationship boundary;
   the current route is owner-only, so this is not a cross-owner exploit.
   **Fix:** search a permission-safe projection, including matching/ranking,
   not merely a sanitized excerpt. Ensure indexes match that projection.
   **Validate:** denied/archived/out-of-scope targets whose only matching text
   or ID occurs in a relationship; permission changes; authorized targets;
   PostgreSQL index/query behavior.

6. **P2 — Returning from a permission edit leaves a falsely current preview.**
   `apps/mobile/src/features/assistant/screens/AssistantScreen.tsx:90,109,137`.
   Focus reloads only status. `previewIsCurrent` compares request JSON, not
   source revisions, permissions, time, or focus lifetime. Preview an item,
   follow a provided link and revoke consent/edit/archive it, then return:
   its old content remains displayed without a stale warning. Search results
   have the same issue. Refresh failure also leaves the prior preview marked
   current. A later send rebuilds context, so the displayed list would not
   reliably describe what is shared.
   **Fix:** invalidate or refresh sensitive results on return and on failed
   refresh; explicitly mark retained offline content stale. Prevent an old
   in-flight response from making an invalidated view current.
   **Validate:** permission revoke, edit/archive, timezone/day change, offline
   return, refresh failure, and delayed responses across focus transitions.

7. **P2 — Search state is not bound to its query/type scope.**
   `apps/mobile/src/features/assistant/screens/AssistantScreen.tsx:115,145,397`.
   Changing text or resource switches keeps old results and cursor. “Load
   more” submits that cursor with the new filters and gets 422; a first-page
   response arriving after a filter change can also populate the wrong view.
   With zero selected types, search silently sends `types=undefined`, which
   searches all types despite the “selected health items” wording and empty
   scope.
   **Fix:** bind result pages and requests to a stable query/type key, reset
   paging on changes, discard stale completions, and explicitly require a
   selection or present an independent all-types search choice.
   **Validate:** query/type changes before and during requests, load-more,
   zero selection, failed searches, and duplicate-free page accumulation.

8. **P2 — Planned context narrowing is incomplete.**
   `services/api/src/health_api/domain/ai.py:AIContextRequest`,
   `application/ai_context_service.py:_eligible_candidates`, and the mobile
   Assistant scope/preview controls.
   The plan requires domains/sections and optional owner narrowing. The DTO
   supports only types and excluded IDs; mobile never sends excluded IDs.
   A sleep task with Events selected admits all opted-in meals/workouts/etc.
   Task text changes ordering only. A user cannot exclude one eligible item
   from this request without changing its global permission. Opt-in alone
   does not provide task-specific minimization.
   **Fix:** add bounded domain/section narrowing and expose per-request item
   exclusion already supported by the server. Define a conservative relevance
   policy that preserves necessary safety constraints; avoid an LLM selector
   or brittle automatic clinical inference.
   **Validate:** domain-specific tasks, unrelated eligible data, per-request
   exclusions preserving canonical permissions, safety constraints, and scope
   parity between preview and send.

9. **P2 — Today context omits existing scheduled intent and occurrence state.**
   `application/ai_context_service.py:_context_entry/_today_summaries`,
   `domain/ai.py:AIContextPack`, and phase 4 planning integration.
   Phase 5 calls for Today and current planning context from completed phases.
   The pack contains raw plan/regimen payloads and actual-log summaries, but
   schedules, due occurrences, completion/skip/reschedule state are stored in
   separate phase 4 tables and are never read. A regimen's dose/instructions
   appear without its canonical frequency; completed intent is invisible.
   **Fix:** include a bounded, minimized scheduled-intent section with parent
   and target permission checks, revision/version evidence, and separate
   intent-versus-actual semantics, or explicitly reconcile this requirement
   as deferred rather than claiming complete Today/planning context.
   **Validate:** due/unknown/completed/skipped/rescheduled items, schedule
   effective versions and DST, permission denied on either parent/target,
   bounds, and no fabricated Event/Observation from completion.

10. **P2 — Custom observations lack usable consent and interpretation support.**
    `apps/mobile/src/features/daily/screens/DailyEditScreen.tsx`,
    `features/planning/screens/TrackerEntryScreen.tsx`,
    `application/ai_context_service.py:_context_entry`, and
    `domain/schemas.py:CustomTrackerValueV1`.
    Tracker creates remain permission-off and custom daily edits render a
    read-only notice instead of the consent form. Owners cannot opt in or
    revoke a custom observation through mobile. The API can nevertheless
    mark one eligible, and context then emits field-ID values plus tracker
    UUID/schema version without immutable field labels/types/units needed to
    interpret them. Arbitrary field IDs need not convey meaning.
    **Fix:** provide permission-only controls without changing immutable
    entry content. Reconcile custom context support: either include minimal,
    authorized immutable schema meaning, or explicitly exclude/identify
    unsupported custom values until that boundary exists.
    **Validate:** opt-in/revoke through UI, old schema versions after tracker
    edits/archive, ambiguous field IDs, missing/false/zero values, unit meaning,
    and no unauthorized tracker-definition expansion.

11. **P2 — The preview does not show the time of individual source entries.**
    `apps/mobile/src/features/assistant/screens/AssistantScreen.tsx:366`.
    Cards display title, provenance, revision, payload and notes but omit
    `content.time` and envelope validity. Two otherwise identical daily
    measurements are indistinguishable by date/time; owners cannot verify
    temporal context despite the “exact Health items” claim. Raw payload JSON
    also substitutes internal keys/IDs for a readable review.
    **Fix:** show source date/instant, timezone, interval and applicable
    validity, preserve unknown/date-only meaning, and provide bounded readable
    values plus owner source navigation. Before live replies, expose actual
    evidence links rather than only their count.
    **Validate:** same-value entries on different days, date-only versus exact
    time, overnight intervals, validity windows, readable large payloads and
    accessible source navigation.

12. **P3 — Omission counts claim precision they do not have.**
    `application/ai_context_service.py:425,447,454` and `domain/ai.py:AIContextPack`.
    Rows beyond the 1,000-candidate cutoff are not counted in
    `omitted_by_budget`; `omitted_by_user` is simply the number of submitted
    IDs, including nonexistent, foreign or already ineligible IDs. A pack with
    2,000 eligible small entries and 100 included can report 900 omissions
    instead of 1,900. `truncated=true` does not clarify that the count is only
    partial.
    **Fix:** expose accurate scoped counts or explicitly named lower bounds /
    unknown totals. Count actual eligible exclusions, not request-list length,
    without revealing foreign-object existence.
    **Validate:** more than 1,000 candidates, byte and entry limits, eligible
    versus nonexistent/foreign/ineligible excluded IDs, and final counters.

13. **P3 — Accepted malformed inputs can escape as 500 errors.**
    `services/api/src/health_api/api/ai.py:83` and
    `application/ai_context_service.py:240,401`.
    A correctly bound base64 JSON cursor with `id:123` raises uncaught
    `AttributeError` in `UUID()`. Accepted calendar-edge `as_of` values raise
    uncaught `OverflowError` during timezone conversion/local-day bounds.
    Probes reproduced both; the API catches `ValueError` only for context.
    **Fix:** strictly validate cursor field types and safe calendar bounds;
    translate expected parsing/range failures to sanitized 422 responses.
    **Validate:** non-string IDs, scalar/list cursor payloads, invalid base64,
    extreme timestamp offsets, minimum/maximum dates with positive/negative
    timezone offsets, and no internal exception response.

14. **P2, before live enablement — Health's adapter response boundary is incomplete.**
    `services/api/src/health_api/api/ai.py:238` and
    `integrations/personal_ai.py:PersonalAIAdapter`.
    The executable injected-adapter path awaits indefinitely, accepts a
    different `request_id`, and trusts provider `context_summary` counts.
    A fake returned a random request ID and `{"invented":999}` with no evidence
    and was accepted. Only cited object/revision pairs and caller-selected risk
    floor are checked. The planned Health-owned deadline/request binding and
    conservative classification are not yet present; callers can label a
    medical message general wellness. Production currently cannot activate
    this path, so these are prerequisites, not active provider incidents.
    **Fix:** enforce the Health deadline with sanitized timeout handling,
    bind completion to the built request, derive inclusion counts in Health,
    validate adapter output, and implement the reviewed deterministic risk
    policy/UX before enabling. Keep protocol-specific callbacks/tool caps
    behind actual contract reconciliation.
    **Validate:** fake never-ending calls, mismatched IDs, invented counts,
    malformed/oversized output, raised/lowered risk, and consequential/urgent
    fixtures with approved presentation. No automatic retry of unknown sends.

## Verification and limits

- API: `.venv/bin/pytest services/api/tests -q` → **113 passed, 46 skipped**.
  PostgreSQL-dependent tests skip without `TEST_DATABASE_URL`.
- Mobile: bundled Node running `node_modules/vitest/vitest.mjs run` from
  `apps/mobile` → **87 passed, 7 failed**; all failures are finding 1.
- Temporary, database-free probes reproduced findings 4, 13, and the response
  correlation/count portion of 14. Compiled PostgreSQL candidate SQL confirms
  missing planning payload date predicates. Probes are outside the repository
  in a disposable temporary directory.
- A disposable PostgreSQL startup was attempted using installed Homebrew tools;
  `initdb` failed with the host's shared-memory limit. Migration execution,
  PostgreSQL retrieval results and query costs remain unverified. No existing
  database or host configuration was altered.
- No device or provider evaluation was performed. `git diff --check` passed.

## Follow-up status

This initial findings snapshot predates the corrections summarized in [Phase 5 release evidence](phase-5-release.md). The release record contains the implemented dispositions and remaining local/provider/device gates.
