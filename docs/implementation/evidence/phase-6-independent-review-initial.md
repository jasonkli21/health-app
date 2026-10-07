# Phase 6 independent review — initial findings (October 6, 2026)

Reviewed October 6, 2026. Scope: `959c56d`, `de89b65`, and `f592b6b`
(HEAD), diff against `af2b531`; reconciled Phase 6 plan/release evidence,
product/UX/security/AI intent, API/domain/application/persistence/migration,
generated contracts, mobile review flow, and existing tests. No substantive
fixes were made. Preserve the pre-existing untracked Phase 5 review document.

**Assessment: corrections are required before local Phase 6 acceptance.**
The closed command union, owner predicates, separate draft store, stable create
IDs, shared transaction/savepoints, provenance links, and disabled provider
boundary are appropriate. No active provider leak or autonomous AI write path
was found. Keeping provider submission, natural-language Add, and AI-prefilled
forms gated is justified by the missing provider contract. A JSON editor is an
accepted local compromise; the findings concern actual semantics and review
requirements, not a demand for a polished editor.

P1 = high priority, fix before use; P2 = normal-priority correctness or missing
requirement; P3 = smaller robustness issue. Line references are at `f592b6b`.

## Actionable findings

1. **P1 — A Profile proposal edit turns omitted fields into destructive clears.**
   `services/api/src/health_api/domain/proposals.py:65`,
   `application/action_proposal_service.py:201,663`, `api/proposals.py`, and
   `apps/mobile/src/features/assistant/screens/AssistantScreen.tsx:94,430`.
   Stored update snapshots preserve omission via `exclude_unset`; response
   serialization expands omitted `notes`, `metadata`, `valid_from`, and
   `valid_to` to null. The mobile editor copies these fields into its PATCH.
   Even a rationale-only edit therefore creates explicit clears, which apply
   removes from the canonical Profile. A deterministic schema roundtrip
   reproduced all four newly explicit nulls. The displayed original command
   also misleadingly shows nulls that the original executor would preserve.
   **Fix:** preserve field presence through response/editor roundtrips; explicit
   null must remain distinguishable from absence. Do not solve this by dropping
   all nulls, since intentional clearing is supported. Regenerate contracts.
   **Validate:** seed notes, metadata, and validity; edit only rationale and
   apply; verify all survive. Cover omitted versus explicitly null versus
   changed values through API serialization and mobile editing.

2. **P2 — Update confirmation does not show the actual changes or side effects.**
   `AssistantScreen.tsx:594` and proposal response construction;
   `application/planning_service.py:530`.
   Cards show a target UUID/revision and the replacement command JSON, without
   existing values, removed fields/items, or a before/after comparison. A
   `plan.update` can remove items and retire their schedules through the reused
   domain service, but this consequence is absent from the confirmation view.
   This misses the plan's exact-diff requirement and weakens informed Save.
   **Fix:** provide revision-bound before/after review for updates, including
   preserved versus cleared optional fields, removed plan items, and schedule
   retirement. Identify targets intelligibly. Retain units/time/provenance.
   **Validate:** Profile clears and preservation, Goal target changes, Plan
   item deletion/reordering, scheduled-item removal, and stale baseline views.

3. **P2 — Refresh silently advances an open editor's concurrency baseline.**
   `AssistantScreen.tsx:210,225,430,461`.
   `beginEdit` saves draft text but no base revision. Returning focus reloads
   the proposal list while retaining that draft; Save uses the latest card's
   `proposal.revision`. If another client edited revision 1 to 2, the old
   revision-1 draft is sent with `expected_revision: 2` and can overwrite those
   edits without a conflict. Evidence is also taken from the refreshed card.
   **Fix:** capture the editor's original revision and evidence/content
   baseline; preserve the draft on conflict and require deliberate review
   before adopting a newer baseline. Prevent stale list/action responses from
   replacing newer proposal state.
   **Validate:** edit, navigate away, concurrent remote edit, return, Save;
   expect conflict and retained draft. Exercise delayed list responses racing
   with edit/apply/reject results.

4. **P2 — Stale evidence/target conflicts have no usable review-and-reconfirm flow.**
   `action_proposal_service.py:253,903`, `api/proposals.py:274`, and
   `AssistantScreen.tsx:363,388,463`.
   Apply records only a generic `reference_changed`/`target_changed` summary.
   Refresh fetches the same proposal snapshot and its old evidence revisions;
   the editor always resubmits those evidence refs and cannot replace them.
   A changed evidence row thus causes both retry and edited draft validation
   to fail indefinitely in the app. A changed target requires manually finding
   its new revision and modifying JSON, with no changed-record review. The
   persisted validation summary is not rendered.
   **Fix:** return sanitized changed-reference hints, load current owner records
   for review, let the user deliberately replace/remove evidence and revise
   target baselines, then save a new proposal revision/hash before confirming.
   Keep uncertain-network recovery distinct from a known stale-data conflict;
   preserve drafts and focus/announce conflict errors accessibly.
   **Validate:** stale/deleted/archived evidence, stale update target, successful
   reviewed replacement, rejected old confirmation, and lost apply response.

5. **P2 — Referenced Goal/Regimen changes are not bound to the confirmation.**
   `domain/proposals.py:101`, `action_proposal_service.py:275,308`, and
   `planning_service.py:_validate_references`.
   Plan commands carry reference UUIDs but no expected revisions for existing
   referenced resources. They need not be in `evidence_refs`. A Goal/Regimen
   can change after proposal creation and still be linked on apply, as long as
   it remains active and of the same type. Row locking stabilizes only the
   current apply transaction; it does not detect changes since review.
   **Fix:** persist/hash base revisions for existing semantic references and
   revalidate them at apply. Preserve the special dependency handling for a
   Goal created earlier in the same proposal. Reuse parent Plan revision for
   schedule changes where it already covers them; avoid redundant versioning.
   **Validate:** mutate a linked Goal or Regimen without changing the Plan or
   explicit evidence; old confirmation must fail, with reviewable recovery.

6. **P2 — Proposal locks invert the existing daily-write lock order.**
   `action_proposal_service.py:275,903`,
   `daily_service.py:656,854`, and `envelope_service.py:unit_of_work`.
   Proposal validation locks referenced HealthObjects before an `event.create`
   calls `create_daily_entry`, which locks User. Ordinary daily update/archive
   locks User before the HealthObject. With a daily row as proposal evidence,
   apply can hold that row and wait for User while an ordinary edit holds User
   and waits for the row: a concrete deadlock cycle. Sorting reference UUIDs
   does not resolve cross-service lock ordering. PostgreSQL should abort a
   transaction rather than permit partial writes, but the request fails.
   **Fix:** establish one lock hierarchy across the proposal executor and
   existing commands, including owner/sequence locks and reference rows.
   **Validate:** barrier-controlled PostgreSQL apply-versus-daily-update/archive
   races, multi-command proposals, and overlapping reference sets. Verify
   completion, one committed effect, and coherent histories/receipts. This is
   code-proven lock inversion, not a locally executed PostgreSQL race.

7. **P2 — Receipt replay ignores proposal revision, and successful alternate keys remain unbound.**
   `action_proposal_service.py:841,865` and
   `persistence/models.py:199` (`ActionCommandReceipt`).
   The prior-key branch compares proposal ID/hash but not proposal revision;
   a mocked receipt replay accepted revision 999 for a revision-2 receipt.
   No-op edits can have the same hash across distinct revisions, so hash does
   not substitute for revision identity. Separately, after apply under key A,
   retry under key B returns success without recording B. B can subsequently
   apply a different proposal, violating the owner-key reuse contract. The
   unique proposal-revision constraint currently permits only one receipt key.
   **Fix:** compare the complete proposal/revision/hash identity in every
   replay branch and durably bind every successfully accepted key to the
   canonical committed result while retaining one effect per proposal.
   **Validate:** wrong revision with correct ID/hash/key; equal hashes across
   edited revisions; A-then-B replay followed by B on another proposal; same
   and different key races; network-loss replay; foreign owners.

8. **P2 — The inbox silently hides proposals beyond the first 50.**
   `apps/mobile/src/features/assistant/api.ts:7` and
   `AssistantScreen.tsx:210,568`.
   The request is unfiltered, includes terminal proposals, and discards
   `next_cursor`. Fifty newer applied/rejected/expired rows can make an older
   pending proposal inaccessible even though it is still valid.
   **Fix:** make pending proposals reachable with a pending view/filter and
   proper pagination; keep terminal history accessible separately as needed.
   **Validate:** more than 50 pending rows, terminal rows crowding a pending
   row, page deduplication, and refresh after an initial load failure. The
   screen already exposes a “Refresh proposals” button after loading errors.

9. **P3 — Draft validation accepts updates to already archived targets.**
   `action_proposal_service.py:341,381,396` versus
   `profile_service.py:313` and `planning_service.py:507`.
   Proposal validation checks target existence/type/revision but omits the
   archived-state rule enforced by execution. A draft for an already archived
   Profile/Goal/Plan can be created or edited with a `valid: true` summary,
   then predictably fails on apply. Archived Profile acceptance was reproduced
   with a mocked aggregate. Execution fails safely; this is misleading draft
   validation, not an archive bypass.
   **Fix:** share the applicable command preconditions at create/edit/apply,
   including target state, without building a second domain implementation.
   **Validate:** already-archived targets and targets archived after creation;
   no target writes and accurate validation/conflict responses.

10. **P2 — Planned current-context/safety revalidation is absent from the executor contract.**
    `action_proposal_service.py:_validate_commands`, `domain/proposals.py`,
    and `docs/implementation/phases/phase-6-implementation-plan.md`.
    The plan requires consulting current constraints/goals/context at apply
    and retaining Phase 5 high-risk policy. The executor checks command
    schemas, explicit evidence, update targets, and Plan references only;
    it captures no safety/context dependency set or task/policy classification.
    Updating a relevant constraint/context outside explicit evidence therefore
    cannot invalidate a reviewed proposal. This is an unimplemented plan
    requirement, not evidence of an active AI medical action: provider
    submission is disabled.
    **Fix:** reconcile the supported policy with concrete command behavior;
    define which current context dependencies must be revision-bound/reviewed
    and which AI action classes remain denied. Implement those deterministic
    checks or explicitly gate unsupported classes before provider enablement.
    Do not invent medical inference or block ordinary manual owner edits based
    on an unspecified clinical rule.
    **Validate:** relevant constraint/context changes invalidate old AI review,
    denied high-risk classes fail closed, allowed owner commands still work,
    and policy checks cannot be bypassed by model-supplied assertions.

11. **P2 — Phase 6 has no executable acceptance coverage.**
    `services/api/tests`, `apps/mobile/tests`, and
    `docs/implementation/evidence/phase-6-release.md`.
    Neither code commit adds tests; no existing test references proposals.
    Thus existing suites do not establish P6.1–P6.5, transaction atomicity,
    confirmation semantics, or the refactored manual-command behavior.
    **Fix:** add focused offline/API/mobile and PostgreSQL integration tests,
    then record actual evidence. Keep unavailable live-provider checks gated.
    **Validate:** all command families; forbidden actions/fields/permissions;
    two-owner isolation on every route; evidence/reference revisions; expiry
    boundaries; edit/old confirmation; compound dependency order; failure
    injection between commands with no residual target/source/history/receipt;
    same/different-key applies and reject/edit races; restart/lost-response
    replay; provenance and permission defaults; manual CRUD regressions;
    migration upgrade/drift and downgrade refusal; mobile draft/review/recovery,
    paging, duplicate taps, focus races, and account switching. Include each
    defect above as a focused regression, rather than tests mirroring helpers.

12. **P2 — Phase 6 adds failures to the configured CI import-order gate.**
    `api/profile.py`, `api/proposals.py`,
    `application/action_proposal_service.py`, `application/envelope_service.py`,
    `application/profile_service.py`, and `domain/proposals.py`.
    Running CI's exact Ruff command with pinned Ruff 0.16.10 reports 24 I001
    failures at HEAD versus 18 on an extracted `af2b531` tree. These six files
    add failures; the release evidence's narrower lint pass does not establish
    the configured gate. The baseline also has separate inherited lint/type
    failures; do not misattribute those to Phase 6.
    **Fix:** conform these import blocks to the repository's effective CI
    configuration and use the exact configured checks in release evidence.
    **Validate:** full CI Ruff check/format and mypy, with inherited failures
    explicitly resolved or tracked. This is required gate repair, not optional
    stylistic cleanup.

13. **P2 — Proposal creation has no independent operational kill switch.**
    `services/api/src/health_api/config/settings.py:95` and
    `services/api/src/health_api/api/proposals.py:181`.
    Settings include proposal TTL but no flag to disable new proposal creation;
    `PERSONAL_AI_ENABLED` is a separate setting and currently rejects being
    enabled. The owner-authenticated POST route remains available regardless.
    The plan requires a switch that can stop proposal generation while leaving
    existing proposals readable and rejectable.
    **Fix:** add a server-side proposal-generation flag and enforce it at the
    create boundary without blocking reads or rejection of existing drafts.
    **Validate:** with generation disabled, POST is denied while existing
    proposals remain readable/rejectable; with it enabled, creation follows
    the configured TTL and owner checks.

14. **P2 — Proposal listing has N+1 evidence reads and can return oversized pages.**
    `services/api/src/health_api/api/proposals.py:157` and
    `services/api/src/health_api/application/action_proposal_service.py:201`.
    The list route serializes every item as a full `ProposalState`. For each
    item, `_state_from_row` loads its revision and then performs a separate
    lookup for every evidence revision. At the 100-item API limit and 20
    distinct evidence references per proposal, this can require roughly
    2,100 lookups; full command payloads can also make one page several
    megabytes. The mobile inbox currently requests 50 items.
    **Fix:** batch-load revisions/evidence and use a bounded summary DTO for
    list pages, loading full command content on proposal detail/review.
    **Validate:** assert bounded query counts and response sizes for maximum
    page/evidence/content fixtures, while confirming detail still returns the
    complete immutable proposal revision.

## Verification and remaining external gates

- API: `.venv/bin/python -m pytest services/api/tests -q` — **122 passed,
  48 skipped**. Skips remain environment-dependent database/integration gates.
- Mobile: bundled Node invoking
  `apps/mobile/node_modules/vitest/vitest.mjs run --root apps/mobile` —
  **95 passed across 20 files**. Mobile TypeScript passes.
- Full configured Ruff format — **63 files formatted**. Ruff check fails as
  described above. Configured mypy reports **6 errors in unchanged
  `application/ai_context_service.py`**, an inherited Phase 5 issue.
- Review probes reproduced omission-to-null changes, archived-target draft
  acceptance, and wrong-revision receipt replay. The latter two used mocks;
  they establish control-flow defects, not database integration acceptance.
- Disposable PostgreSQL initialization in a disposable temporary directory failed with
  `shmget(..., size=56) ENOSPC`, including an elevated attempt. No database
  server started; no existing cluster/shared IPC was modified. Migration
  execution, ORM drift, atomic rollback and real races remain unverified.
- `git diff --check` passes. Implementation files were not edited.
- Provider identity/delegation/tool registration, retention, real high-risk
  policy integration, staging smoke, and device confirmation/accessibility
  walkthrough remain external gates. Supply actual contracts/configuration;
  do not fabricate a provider or claim live Phase 6 acceptance.

## Follow-up status

This initial findings snapshot predates the corrections summarized in [Phase 6 release evidence](phase-6-release.md). The release record contains the implemented dispositions and remaining database/provider/device gates.
