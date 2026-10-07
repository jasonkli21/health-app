# Phase 4 independent review — initial findings (October 5, 2026)

Reviewed October 5, 2026. Scope: `65d82dd` through `e044428` inclusive (diff
against `d835d95`), the reconciled phase 4 plan, ADR 0008, product/UX/security
intent, API/domain/application/persistence changes, migration, generated
contracts, mobile flows, and existing tests. No substantive fixes were made.

**Assessment: not ready for acceptance.** The canonical-store approach, manual
provenance, owner-scoped queries, immutable tracker definitions, and separation
of intent from actual logs are appropriate. The issues below are actionable
runtime defects or missing product/contract behavior, not a cleanup wishlist.
P1 means a blocker or serious regression/privacy issue; P2 means normal-priority
correctness or requirement work; P3 means a smaller usability defect.

## Findings

1. **P1 — ORM configuration fails across the application.**
   `services/api/src/health_api/persistence/models.py:164,393,453`.
   Adding `observations(owner_id, tracker_id) -> health_objects` introduces a
   second FK path alongside the Observation envelope FK. Both sides of
   `HealthObject.observation_item` / `ObservationItem.health_object` leave the
   relationship implicit. Importing models and calling `configure_mappers()`
   raises `AmbiguousForeignKeysError`; ORM construction/queries configure the
   same registry, so this also blocks existing Profile/auth/daily operations.
   **Fix:** specify the envelope join/foreign columns on both relationships.
   **Validate:** database-free mapper initialization plus existing and new
   owner/auth/Profile/Event/Observation/planning integration smoke tests.

2. **P1 — Standard Observation writes violate the new tracker constraint.**
   `application/daily_service.py:145–156`, `persistence/models.py:391,460`, and
   migration `d4e5f607a8b9` (paths under `services/api/src/health_api` unless
   otherwise stated). `_observation_fields` explicitly assigns
   `tracker_values=None` for ordinary measurements/severity. Its JSONB column
   uses the default `none_as_null=False`: the psycopg bind processor produces
   `Jsonb(None)`, i.e. JSON `null`. `ck_observations_tracker_shape` requires SQL
   `tracker_values IS NULL` for non-custom rows. After fixing #1, standard
   creates/updates, including compound symptom saves, therefore fail.
   **Fix:** consistently store SQL NULL for absent tracker data.
   **Validate:** PostgreSQL create/update of weight and linked severity,
   compound rollback, custom-to-standard conversion where allowed, and direct
   checks of SQL NULL versus JSON null.

3. **P1 — Late tracker-save failures repopulate another account's recovery state.**
   `apps/mobile/src/features/planning/screens/TrackerEntryScreen.tsx:190–218`,
   `features/planning/api.ts`, `app/_layout.tsx`, and `auth/authenticatedFetch.ts`.
   Start a tracker save as A, switch/sign out, then let the old response settle.
   The layout clears recovery and remounts, but authenticated fetch rejects the
   old request with `SessionChangedError`; the unguarded old catch treats this
   as uncertain and writes A's request/values back into the global recovery
   singleton. B's tracker form can recover that private draft and retry it.
   **Fix:** bind attempts and post-await side effects to owner/session epoch;
   stale continuations must neither restore/clear recovery nor navigate.
   **Validate:** deferred network/body/token failures across A→B and sign-out,
   including a new B attempt already in progress. Check shared daily recovery
   callers for the same inherited pattern while implementing this fix.

4. **P2 — Planning create retries can duplicate resources.**
   `apps/mobile/src/features/planning/screens/PlanningEditorScreen.tsx:282–434`.
   Every submission generates a fresh UUID. If a create commits but its
   response is lost, retry creates a second goal/regimen/plan/context/tracker.
   The backend's fingerprint/idempotency support is never used for recovery.
   **Fix:** retain the original ID and canonical request through uncertain
   results and route remounts, with owner scoping and explicit recovery before
   allowing changed content; use established recovery conventions.
   **Validate:** commit-then-network-failure, identical retry, changed draft,
   navigation away/back, and account switch for all five resource kinds.

5. **P2 — Schedule edits erase the visible state of already recorded future slots.**
   `application/planning_service.py:649–665,958–1006`.
   Occurrences are regenerated exclusively from the latest effective version.
   Mark a future slot completed/skipped, then edit its time or recurrence
   effective before that slot: the original key is no longer expanded and the
   new slot is unknown (or the old slot disappears entirely). Rescheduled
   overrides can similarly disappear when their original slot stops matching.
   Current parent pause/completion/archive also makes occurrence reads return
   `[]`, including previously recorded history.
   **Fix:** preserve recorded occurrence identity, schedule provenance, and
   readable history independently of later schedule/lifecycle edits; suppress
   replaced unrecorded intent without losing recorded assertions.
   **Validate:** pre-recorded future completion/skip/reschedule followed by
   time, weekday, interval, zone, and lifecycle changes; unchanged keys retain
   state and no replacement duplicate is shown.

6. **P2 — Completing/skipping a moved occurrence moves it back to its original date.**
   `application/planning_service.py:941–989,1068–1078,1141–1146` and
   `persistence/models.py`'s override reschedule-shape constraint.
   Moving Oct 10 to Oct 12 then completing it clears `rescheduled_at`.
   Expansion uses the original due instant whenever state is not `rescheduled`,
   and moved-date discovery searches only rescheduled state. Oct 12 loses the
   recorded moved item; Oct 10 receives its completion. This conflates action
   state with the occurrence's effective due time.
   **Fix:** retain the moved due instant independently of completed/skipped
   state and use it for discovery/presentation.
   **Validate:** move→complete, move→skip, move again, retries, and date-window
   queries on both original and destination days.

7. **P2 — Schedule edits reject the default UI request and force recurrence reanchoring.**
   `api/schemas.py:210–223`,
   `apps/mobile/src/features/planning/screens/ScheduleEditorScreen.tsx:85–97,145–161`.
   The editor retains the existing `start_date` but advances `effective_from`
   to tomorrow. `ScheduleEditRequest` requires start_date ≥ effective_from,
   so a routine time edit returns 422. Moving start_date to satisfy validation
   also resets daily/weekly interval alignment unnecessarily.
   **Fix:** distinguish the original recurrence anchor from the new version's
   effective boundary, allowing future-effective edits to preserve alignment.
   **Validate:** default UI edit of an existing schedule, every-two-days/weeks
   alignment, and future pending versions, without requiring users to alter
   the original start date.

8. **P2 — Occurrence eligibility ignores resource validity and referenced lifecycle.**
   `application/planning_service.py:list_planning_occurrences,
set_planning_schedule,record_occurrence_action,_validate_references`.
   Plan/regimen start/end dates are stored but never constrain expansion or
   occurrence commands. An expired or not-yet-valid resource still appears
   and accepts actions if its schedule permits it. A scheduled plan item
   referencing a regimen keeps appearing when that regimen is explicitly
   paused/completed/archived, because only the enclosing plan is checked.
   Conversely, archiving a referenced object makes even unrelated edits to
   the existing plan fail reference validation.
   **Fix:** define and enforce parent/target validity and lifecycle eligibility
   for future intent; retain old links and recorded history, and permit
   unrelated edits of plans with historical inactive references.
   **Validate:** before/after validity boundaries, pause/resume/archive of a
   referenced regimen/goal, existing-plan rename/reorder, and direct actions
   outside eligibility. Preserve the rule that contexts do not pause regimens.

9. **P2 — Repeated references bypass plan-item subtype validation.**
   `application/planning_service.py:140–181`.
   Required kinds are collected into a dict keyed only by target UUID. A
   `regimen` item pointing at a Goal followed by a valid `goal` item pointing
   at that same Goal overwrites the expected kind and both are accepted.
   **Fix:** validate each edge's required subtype, or reject conflicting kind
   expectations for a repeated target. **Validate:** both item orders,
   repeated valid references, wrong subtype, and foreign-owner references.

10. **P2 — Noncanonical occurrence keys create invisible/duplicate actions.**
    `application/planning_service.py:719–741,1014–1159`.
    Parsing accepts alternate base64/JSON encodings of the same schedule/date/
    time, but override persistence uses the supplied raw string. A padded key
    or JSON with different whitespace/order can therefore be acted on while
    canonical occurrence reads still show unknown, bypassing one-slot
    identity/idempotency. A numeric `s` also raises uncaught `AttributeError`
    in `UUID(...)`, giving 500 rather than a controlled invalid-key response.
    **Fix:** strictly validate types and canonicalize or reject aliases before
    lookup/write. **Validate:** padding, whitespace/order, UUID/date variants,
    malformed shapes/types, same-slot retry, and owner isolation.

11. **P2 — Optional tracker inputs can fabricate zero; selections cannot be cleared.**
    `apps/mobile/src/features/planning/screens/TrackerEntryScreen.tsx:103–137,334–406`.
    Numeric/quantity omission checks run before trimming, so whitespace becomes
    `Number("") === 0`; required numeric whitespace also passes. Optional
    boolean/enum fields have no way to return to absent after selection.
    **Fix:** normalize blank numeric input before required/omission checks and
    offer an unset action for optional selections, preserving explicit false
    and zero. **Validate:** untouched/whitespace/zero/false values, required
    blanks, and selecting then clearing optional boolean/enum fields.

12. **P2 — Valid transport inputs can escape validation as runtime exceptions.**
    `domain/planning.py:330–358`, `domain/scheduling.py`, and
    `application/planning_service.py:934–939`.
    Custom values have an open transport map; `isfinite(10**400)` raises
    `OverflowError` before the magnitude rejection, producing 500 for number
    and quantity fields. Occurrence `start_date=0001-01-01` also underflows
    because subtraction happens before `max(date.min, ...)`. Schedule schemas
    accept dates/local instants whose UTC conversion or increment cannot be
    represented. **Fix:** bound/type-check before conversion/arithmetic and
    translate unsupported ranges to the established 422 response.
    **Validate:** huge integer number/quantity requests, min/max calendar
    bounds and extreme zone offsets, alongside normal leap/DST fixtures.

13. **P2 — Mobile lists and reference/entry pickers silently stop at 100.**
    `PlanningOverviewScreen.tsx:38–59`,
    `PlanningEditorScreen.tsx:145–182`, `TrackerEntryScreen.tsx:52–80`
    under `apps/mobile/src/features/planning/screens`.
    All request one page with limit 100 and discard `next_cursor`. Older plans,
    trackers and reference targets become inaccessible once a group exceeds
    100, despite a paginated API and no corresponding creation limit.
    **Fix:** support bounded user-driven pagination/search in lists and
    pickers, including loading/error states. **Validate:** >100 resources,
    later-page tracker logging/reference selection, stable pages and retry.

14. **P2 — Archived resources and ended contexts have no durable discovery path.**
    `application/planning_service.py:378–385`, planning list routes, and
    `PlanningOverviewScreen.tsx:144–215`.
    Lists always filter envelope status active and expose no archive filter;
    the overview additionally hides ended contexts. The immediate post-archive
    detail can be read, but after leaving it neither archived resources nor
    ended contexts can be found again through the product. “Available in
    history” is consequently misleading.
    **Fix:** provide an owner-scoped archived/ended list or history discovery
    flow, retaining read-only detail and immutable tracker decoding.
    **Validate:** archive/end, leave/restart the client, rediscover and read
    resource/history/old tracker entries, with no new logging to archives.

15. **P2 — Editors do not recover current data after child navigation/conflicts.**
    `PlanningEditorScreen.tsx:145–247,282–434`,
    `ScheduleEditorScreen.tsx:74–106,173–179`, and overview mount-only loading.
    Editing a schedule increments the parent envelope revision; `router.back()`
    returns to the still-mounted parent editor whose original revision is
    stale. Its next save fails 409. Editors provide no reload/refetch action
    for 409 or failed initial loads; an initial detail failure leaves an edit
    form that submits to a newly generated ID with revision 0. Returning from
    a child also leaves overview/picker data stale.
    **Fix:** use focus/invalidation and explicit conflict/retry handling while
    preserving unsaved drafts; disable edit submission until the intended
    resource is loaded. **Validate:** schedule-child save→parent save, failed
    load→retry, stale update→reload/reconcile, and create/edit on nested routes.

16. **P2 — A scheduled plan item can never be removed.**
    `application/planning_service.py:462–475`, schedule FK retention, and
    `PlanningEditorScreen.tsx`'s Remove action.
    Every item with any schedule identity is permanently required in the
    candidate item set, even after its schedule ends and without recorded
    occurrences. The UI offers Remove, but saving always rejects it; there is
    no schedule retirement/item-removal operation.
    **Fix:** support retirement/removal of future intent while retaining the
    stable item and versions needed by historical records. No destructive
    history cascade. **Validate:** removal of unscheduled, scheduled-unrecorded,
    ended and recorded items; future Today disappears and history survives.

17. **P2 — Planning does not expose the inherited permission contract.**
    `api/schemas.py:162–207,284–304`, `api/planning.py:resource_response`, and
    planning create/update services.
    New envelopes correctly default both AI/cross-domain flags to false, but
    CRUD accepts neither flag, responses omit them, and no permission route
    exists. Users cannot inspect or explicitly authorize use of any planning
    resource in the upcoming permission-respecting context builder. This
    falls short of the plan's inherited permission semantics.
    **Fix:** expose explicit owner-controlled permissions using established
    envelope conventions and revision history, with safe defaults unchanged.
    **Validate:** default false, deliberate opt-in/out, stale writes, snapshots,
    client contract regeneration and two-owner access.

18. **P2 — The optional actual-record association is incomplete.**
    `api/schemas.py:OccurrenceActionRequest`,
    `application/planning_service.py:1079–1100`, override/action models, and
    Today action UI.
    The plan calls for optional linkage to an existing owner Event or
    Observation. Implementation supports only `linked_event_id`, and mobile
    offers no association flow at all; tracker/measurement Observations cannot
    be linked. **Fix:** add a typed, owner-validated Event/Observation reference
    and a usable explicit association path, preserving assertion-only
    completion. An atomic log-and-complete command is needed only if that
    combined UI is offered. **Validate:** both record types, foreign/missing/
    archived IDs, retries and rollback of any combined command.

19. **P2 — Recorded action history is write-only; schedule history is hidden.**
    `application/planning_service.py:1150–1163`, `api/planning.py`, and
    `PlanningHistoryScreen.tsx:119–130`.
    `PlanningOccurrenceAction` is written but never queried/exposed; resource
    history does not contain actions. Schedule snapshots add `schedule`, but
    mobile renders only `snapshot.payload`, hiding the schedule change. Users
    cannot review the action timestamps/changes promised by the history
    contract. **Fix:** expose bounded owner-scoped occurrence history and
    render schedule/action changes with their actual provenance/time.
    **Validate:** multiple state/reschedule changes, schedule versions,
    historical reads after lifecycle/archive, and history pagination.

20. **P2 — Today limits count irrelevant contexts and occurrence reads perform excessive queries.**
    `application/planning_service.py:888–1008,1174–1262`.
    Contexts are limited to 501 before validity filtering: 501 expired/future
    contexts still in active lifecycle make all Today requests fail, even with
    zero applicable contexts. Schedule expansion also queries one version and
    one override per candidate date per identity, plus parent/label queries;
    50 weekly items over a valid 31-day window can require roughly two thousand
    queries even when the result fits the 500-item cap. Every Today timeline
    continuation repeats planning expansion.
    **Fix:** apply applicability before result limits, batch schedule versions/
    overrides/labels for the bounded window, and avoid repeated unnecessary
    expansion on continuation reads. Keep existing daily snapshot semantics.
    **Validate:** >500 irrelevant contexts with few applicable ones, explicit
    overflow behavior, query-count bounds for 50-item plans/31 days, and Today
    paging under concurrent planning edits.

21. **P2 — Tracker builder generates duplicate field IDs after removal.**
    `apps/mobile/src/features/planning/screens/PlanningEditorScreen.tsx:784–813`.
    Add field_2 and field_3, remove field_2, then add a field: the generator
    uses the current array length and creates a second field_3. Saving rejects
    the definition; field IDs also serve as value-map identity, so they must
    remain distinct and stable. **Fix:** allocate a new unused field ID without
    renumbering existing fields. **Validate:** repeated add/remove cycles,
    definitions with user-edited IDs, and old entries after schema edits.

## Verification and acceptance handoff

- Existing API suite: **90 passed, 43 skipped** using
  `.venv/bin/python -m pytest services/api/tests -q`. PostgreSQL tests skipped
  because no `TEST_DATABASE_URL` was supplied.
- Existing mobile suite: **79 passed across 16 files**, run using the bundled
  Node binary and `apps/mobile/node_modules/vitest/vitest.mjs run`. The normal
  pnpm entry point initially rejected globally installed pnpm 11 (repo needs
  pnpm 9); no dependency changes were made.
- There are **no phase 4 API/domain/persistence/mobile tests** in those suites.
  Passing existing tests therefore does not establish phase 4 acceptance.
- Database-free runtime probes reproduced #1, #7, #9, #10 and #12. SQLAlchemy's
  actual psycopg JSONB binding established #2's JSON-null behavior. Service
  probes with mocked persistence demonstrated #5's unknown state after a time
  change and #6's clearing of the moved due time. These are not substitutes
  for PostgreSQL integration tests.
- A disposable `initdb` attempt under a disposable temporary directory failed with host System V
  shared-memory exhaustion (`shmget: No space left on device`), matching the
  inherited Phase 2 blocker. No existing database/cloud/user data was touched.

## Follow-up status

This initial review snapshot records findings before the correction commit. Its findings were addressed and later audited; see [Phase 4 audit evidence](phase-4-audit.md) for the follow-up verification and remaining acceptance gates.
