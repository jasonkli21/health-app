# Phase 6 — Typed AI action proposals and confirmation

## Implementation-time reconciliation gate

**Status: implementation in progress. Dependencies: locally delivered Phases 1–5 and their actual release evidence.** Read [Phase 6 roadmap](../implementation-plan.md#phase-6--ai-action-proposals), ADR 0006, actual Phase 5 evidence, owner/source/revision/permission schemas, Profile/daily/planning command contracts and mobile form flows. Identify actual external proposal capability support; record drift and update material plan/ADR changes before code.

Actual scaffold homes are API domain/application/api/persistence/integrations/config, API tests, root migrations/contracts, api-client and mobile app/src/tests. All proposed artifacts below are **planned/provisional**; previously completed product modules must be inspected rather than assumed by filename.

### Reconciliation before implementation — October 5, 2026

- Phases 1–5 have local release evidence. The actual owner-authenticated APIs
  and application commands are in `services/api/src/health_api`; generated
  client artifacts are in `contracts/openapi` and `packages/api-client`; the
  mobile Assistant is under `apps/mobile/src/features/assistant`.
- Phase 5 explicitly has no supplied Personal AI endpoint, service identity,
  end-user delegation, callback/tool protocol, or retention contract. The
  only adapter is disabled and `PERSONAL_AI_ENABLED=true` is rejected. There
  is therefore no supportable live `health.propose.*` registration or AI
  caller identity to implement. Proposal creation by a provider remains
  disabled until that contract is supplied; no provider URL or credential is
  guessed.
- Existing source metadata can represent `ai` and user-confirmed state, but
  `health_object_revisions` constrains actors to the owner and does not record
  a proposal reference. Existing command services each own a transaction and
  hard-code manual provenance. These are real reuse gaps for a one-transaction
  proposal executor and will be changed before composing commands.
- Proposal drafts are not canonical health facts. Persist them in dedicated,
  owner-scoped proposal, immutable proposal-revision, event, and receipt
  tables. This avoids putting pending state in `health_objects` or changing
  its clinical resource allowlist. Applying a command will call existing
  domain services in a shared outer unit of work, preserving their schema,
  owner-reference, and history validation.
- The plan's live-provider package is gated, not simulated. This delivery
  implements the fail-closed proposal core and owner-confirmation path where
  the repository can verify them. It must report provider submission,
  provider role/delegation, and live confirmation walkthrough as unresolved
  external gates.

ADR 0006 and this plan were reconciled before code to record these actual
service and persistence boundaries.

## Outcome / strict deliver and defer

**Deliver:** profile create/update, Event creation (including explicitly linked supported Observations), goal create/update, plan create/update and tracker-definition creation as typed proposals. User previews, edits, confirms/rejects them; one transactional executor applies approved changes with provenance/history and idempotency.

**Defer:** autonomous changes, bulk destructive/archive/delete proposals, regimen/context-specific proposal commands unless explicitly added by an approved contract extension, automated insight/recommendation generation to Phase 7, record extraction proposals to Phase 9, device import/web. Existing manual CRUD remains available. Personal AI may create proposals but cannot apply them or approve itself.

## Proposal state machine / persisted contract

Use existing health_objects envelope/source/history for identity and owner, with planned `action_proposals` subtype. Fields: proposal kind, schema_version, originating request/conversation reference, AI source metadata (no credential), bounded rationale, evidence object+revision refs, normalized typed commands, target/base revisions, canonical content hash, created/expiry instants, state and last validation summary. Default expiry24h/max7days, configurable server-side with explicit reason. Expiry is checked at apply even without a background process.

States: `pending -> applied|rejected|expired|superseded`; application conflict/validation failure leaves pending with structured error until reviewed/rejected/expired. Editing creates a new immutable proposal revision/content hash and supersedes the prior confirmation view; never change the payload of an already-applied proposal. Do not persist an `applying` state that can get stranded after process failure; use transaction locks and final terminal state. Applied stores result IDs/revisions, confirmed_by user, confirmed_at, command receipt reference and applied_at. Rejected records actor/time and optional bounded reason; no target writes.

Typed command union uses established domain request schemas, not SQL/JSON patches/unrestricted endpoint names:

| Command                            | Target/version requirements                                                                                  |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `profile.create`, `profile.update` | Create stable UUID or owner target + expected_revision; Profile payload/version/validity                     |
| `event.create`                     | Supported Phase 2 Event schema + optional bounded linked Observation commands, stable UUIDs and atomic links |
| `goal.create`, `goal.update`       | Phase 4 goal schema; update expected_revision                                                                |
| `plan.create`, `plan.update`       | Stable items/owner references; update plan/schedule base revisions if relevant                               |
| `tracker.create`                   | Phase 4 safe primitive definition schema; immutable version rules                                            |

Maximum10 commands/proposal, total payload64KB; new IDs allocated on proposal creation and retained across retries. Commands execute in declared dependency order (create target before linking); reject cycles/missing references/duplicate conflicting commands. Unsupported schemas/actions/units/owners/evidence IDs or permission changes reject at creation and again at apply. Proposal may not grant AI-use/cross-domain permissions; those are separate explicit user settings. Constraints/goals/context consulted at apply with current revisions; proposing medical content does not bypass high-risk Phase 5 policy. Server validates rather than trusting model assertions. Quantities/sparse/time/schema semantics identical to manual command services.

Source after apply remains `ai` origin + `user_confirmed` confirmation, with original external/request/evidence metadata and user edits recorded. It must not be relabeled manual solely because confirmed. Store minimal rationale/evidence needed for audit; no chain-of-thought or entire conversation dump. Target history actor records confirming user and proposal ID; proposal history and target history share a commit boundary. AI eligibility does not become true by inference.

## Apply transaction and authorization

Planned `command_receipts` holds owner, proposal ID/revision, idempotency key, canonical command hash and committed result; unique owner+key and proposal applied revision. It is an explicit reliability addition here, not a message queue. Scope key max128 opaque characters. Same key/hash returns committed result even after network loss; key reuse with different proposal/content returns409. Same proposal concurrently applied under different keys still creates one result via row lock/unique applied state and returns the original result. Do not rely on in-memory locks.

Apply order in **one DB transaction**: authenticate normal user; owner-load and lock proposal; verify pending/current revision/hash and expiry; verify explicit confirmation of the viewed revision; resolve every owner reference/current target revision; revalidate current schemas/constraints; call existing application commands using the shared transaction; append source/target/proposal histories and receipt; mark applied and commit. Refactor command transaction ownership only as necessary to support a unit of work; no duplicate validation or second proposal-only domain implementation. No external AI call while holding this transaction. Injected failure at any command rolls back all target/history/receipt changes. On stale target409, return sanitized changed-reference hints, refresh preview and require confirmation again; never auto-rebase or infer merge.

Normal user auth alone can apply/reject/edit. Service delegation may use new narrow `health.propose.*` capabilities to submit pending drafts only; it cannot reach domain mutation routes, apply routes, raw owner IDs or privilege grants. Existing Phase 5 read scopes unchanged. User consent must not be inferred from a chat sentence such as “sounds good”; use a deliberate app Save/Confirm action tied to displayed revision. Server capability enforcement is independent of model prompt.

## API / confirmation UX and direct-save exception

Planned `POST /action-proposals`, list/detail/history endpoints, `PATCH /action-proposals/{id}` for reviewed pending content with expected proposal revision, `POST /action-proposals/{id}/apply`, and `/reject`. Use existing sanitized error envelope; list default50/max100, bounded state filters and stable cursor. Apply body `{proposal_revision, content_hash, idempotency_key, confirmation: 'explicit_user_save'}`; derive confirmer from verified user token, never body. 404 foreign/missing, 409 stale/hash/key/terminal mismatch, 410 expired, 422 unsafe/invalid command, 503 DB failure. Applied response includes immutable results; retries return same results. GET must not auto-apply; expiry can be derived/transitioned safely without target mutation.

Assistant UI gains pending proposal cards/details showing exact added/changed fields, time/unit, provenance, evidence and uncertainty, plus edit/confirm/reject. Refresh stale evidence/targets and require review when content changes. Pending/expired/rejected/applied/conflict/network-uncertain states are distinct. Disable duplicate taps but use server idempotency for correctness. On unknown network outcome poll proposal/result with same owner/key, never emit fresh command IDs.

**Explicit direct-save exception:** user already inside a structured create/edit form may review AI-populated fields and tap Save as the confirmation; no second redundant confirmation dialog is required. For this phase, reuse proposal validation/apply/audit behind that Save action, allowing immediate application with the viewed proposal revision. General conversation always creates pending proposals. Existing purely manual forms still call manual commands normally. This implementation chooses one backend apply path rather than a separate unreviewed AI write route; it satisfies ADR 0006 without inventing a second executor. Server-created origin metadata cannot be spoofed by arbitrary client `source` fields.

Natural-language universal Add can now ask Personal AI for supported proposal types using Phase 5 bounded context/delegation and show a preview before save. Disabled AI leaves structured Add working. No auto-event logging from recommendations. Accessibility includes focus on diff/conflict errors, clear action labels and draft preservation in memory.

## Order and packages

`P6.1 command/state contract -> P6.2 transactional executor -> P6.3 proposal API/tool adapter -> P6.4 review/form UX -> P6.5 adversarial/race verification`. Fakes/fixtures can run parallel to executor once contracts freeze; live proposal registration waits for authorization tests.

### P6.1 — Define safe commands and proposal lifecycle

**Dependencies:** reconciliation. **Goal:** executable bounded schema/state rules.

**Areas:** domain registry/application commands/docs; provisional proposal schemas and migrations design.

**Work:** typed command union, limits/evidence/base revisions/expiry, state transitions, origin/confirmation and direct-save mapping; enumerate existing command-service reuse points.

**Requirements:** no generic patches, deletes or permission escalation; no inferred consent. **Tests:** each allowed/disallowed command, extra fields, cycles, expired/stale/evidence/quantity/owner fixtures. **Acceptance:** all supported proposals validate against existing phase schemas. **Out of scope:** extraction/recommendation extensions.

### P6.2 — Persist proposals and apply atomically

**Dependencies:** P6.1. **Goal:** exactly one committed effect.

**Areas:** migrations/persistence/application/tests; provisional proposals/receipts/history services.

**Work:** additive proposal/receipt tables and uniqueness, immutable payload revisions, locks/unit-of-work, command execution/history and terminal results; reject/expiry behavior.

**Requirements:** all-or-nothing health+audit+receipt; server-owned timestamps/source; no network under DB locks. **Tests:** PostgreSQL parallel applies (same/different keys), failure at each command, restart/network-loss replay, stale target/content, apply/reject race and boundary expiry. **Acceptance:** repeated/colliding requests never duplicate mutations or split histories. **Out of scope:** queues/distributed locks/background actions.

### P6.3 — Expose owner-safe proposal APIs/tools

**Dependencies:** P6.2 and Phase 5 live/fake adapter. **Goal:** narrow propose capability with user-only apply.

**Areas:** API/integrations/capability registry/client/OpenAPI/tests.

**Work:** routes/error/result DTOs, read/propose tool mapping, deny apply to services, bounded provider responses, generation and audit metadata.

**Requirements:** no service token accepted as user confirmation; retry identity remains stable. **Tests:** role/owner matrix on every endpoint, forged owner/source/hash, malformed provider response, write-tool escalation and disabled AI. **Acceptance:** AI can submit a pending proposal and only verified owner can apply. **Out of scope:** broad service write scopes.

### P6.4 — Review, edit, confirm and direct-form Save

**Dependencies:** P6.3 generated contract. **Goal:** informed recoverable user control.

**Areas:** mobile Assistant/Add/Profile/Plan forms and separated tests; provisional proposal-review feature.

**Work:** exact diffs/evidence/time/unit, editable pending draft revision, rejection, stale refresh/reconfirmation, explicit form Save and natural-language Add preview.

**Requirements:** no duplicate confirmation dialog for explicit Save; no silent background apply; in-memory privacy and accessibility. **Tests:** all proposal kinds, edit→old confirmation invalid, double tap/lost response/retry, expiry/conflict/reject and optional AI unavailable. **Acceptance:** each authorized kind can be reviewed and safely saved once. **Out of scope:** recommendation creation/autonomous planning.

### P6.5 — End-to-end proposal safety review

**Dependencies:** all packages. **Goal:** trustworthy executor for later phases.

**Areas:** integration/evaluation tests, AI/security/API docs; provisional phase-6 evidence.

**Work:** synthetic multi-command replay, adversarial model/tool text, real provider proposal check where enabled, audit/privacy inspection and manual app confirmation walkthrough.

**Requirements:** live policy limitations stay explicit. **Tests:** DB invariants before/after failures, no change before confirmation, existing manual regression and log redaction. **Acceptance:** evidence proves no uncontrolled AI mutation. **Out of scope:** claiming model-generated medical actions are safe by default.

## Migration, rollback, verification and phase acceptance

Additive proposal/receipt tables preserve existing object history. Reject unknown command/schema versions safely; keep applied payload/result decoders even after upgrading proposal schema. Feature flag can disable proposal generation while owner can still inspect/reject existing pending proposals. Apply rollout must support current receipt format; never delete receipts during operational rollback or retry may duplicate effects. Data restoration/reversal is an explicit compensating user command, not automatic rollback of previously confirmed facts. A failed transaction needs no compensating target cleanup.

| Risk                  | Deterministic offline/DB tests                                            | External/manual                            |
| --------------------- | ------------------------------------------------------------------------- | ------------------------------------------ |
| Consent/roles         | User vs service/owner authorization, no effects before apply              | Actual proposal-tool registration          |
| Idempotency/atomicity | Concurrent PostgreSQL applies, injected failures, receipt replay          | Network-loss device walkthrough            |
| Temporal/provenance   | Source/revision/evidence/expiry golden assertions                         | Exact diff readability/accessibility       |
| Schema/safety         | Malformed commands/injection/permission escalation fixtures               | Phase 5 live high-risk policy verification |
| Compatibility         | Manual routes, migrations, generated client and disabled-mode regressions | Current deployed staging smoke             |

Accept when all five requested proposal families work, every AI-originated mutation needs explicit user Save/Confirm, receipt/history/source relationships survive retries/races, and manual/disabled modes remain useful. No later-phase integration.

Before Phase 7: Is there exactly one transactional executor? Does any service token bypass confirmation? Are stale views invalidated and reviewed again? Are origins preserved after edits? Can later recommendations/extraction reuse the same mechanism without direct writes?

Implementing Luna Max must create planned `docs/implementation/evidence/phase-6-release.md`: actual commands/states/API fields, migrations/head, transaction/receipt uniqueness rules, provenance/history examples, explicit-save UX contract, role/tool matrix, generated procedure, concurrency/failure and live provider results, flags and unresolved checks. Include extension instructions for Phase 7/9 without preimplementing their commands.
