# Phase 5 — Read-only Personal AI integration

## Implementation-time reconciliation gate

**Status: local implementation delivered; live integration remains gated. Dependencies: accepted Phases 1–4 with actual release evidence.** Read [Phase 5 roadmap](../implementation-plan.md#phase-5--personal-ai-integration), [AI boundary](../../ai/personal-ai-integration.md), security docs/ADRs and actual permission/context/identity APIs. Inspect the actual Personal AI service repository or its supplied API/auth/tool contract before writing a live adapter. Record drift; materially changed boundary/protocol requires updated plan/ADR before code. See [Phase 5 release evidence](../evidence/phase-5-release.md) for implemented scope and open gates.

Real scaffold locations: API `application`, `domain`, `api`, `integrations`, `config` directories; `services/api/tests`; `contracts/openapi`; `packages/api-client`; mobile `apps/mobile/app`, `apps/mobile/src/features`, and `apps/mobile/tests`. The task descriptions below preserve the original planning baseline; local delivery, actual paths, deviations, and release gates are recorded in [Phase 5 release evidence](../evidence/phase-5-release.md). Prior product code and the external Personal AI service were prerequisites to reconcile, not assumed interfaces.

### Reconciliation before implementation — October 5, 2026

- Phase 4 is implemented locally through the reviewed checkpoint in
  [`phase-4-release.md`](../evidence/phase-4-release.md). The actual mobile
  homes are `apps/mobile/app`, `apps/mobile/src/features`, and
  `apps/mobile/tests`; the path shorthand above is stale. Phase 4 exposes
  Profile, daily, planning, tracker, schedule, context and Today APIs, with
  existing per-object `ai_use_allowed` flags on `health_objects`.
- This repository contains no Personal AI service, endpoint definition,
  service identity, user-delegation contract, tool callback protocol, or
  retention terms. Phase 3 supplies Firebase end-user identity only. The
  `.env.example` `PERSONAL_AI_BASE_URL` is an unsupported placeholder and is
  not evidence of a service. There are no AI context/search/assistant routes
  or full-text search indexes.
- Profile and planning create/edit flows can explicitly set AI permission.
  Daily Event/Observation creation hard-codes it off and their edit requests
  cannot change it. All create defaults in the existing model are restrictive.
- The canonical model has source kind and confirmation status, but no source
  confidence score. Pack entries carry the available provenance fields;
  confirmed items rank first within each deterministic relevance class, while
  source kind is shown without inventing an unvalidated confidence weighting.
- The live adapter and delegated callback portions of P5.3 cannot be
  implemented against a guessed protocol. This implementation adds typed
  Health-owned context/search/message contracts, bounded owner-scoped reads,
  and an adapter that is disabled by default and refuses activation without
  the external contract. It will not send health data to an invented endpoint.
  Assistant preview and search remain useful offline; message submission
  returns a sanitized unavailable response while the adapter is disabled.
- Add explicit daily-item permission controls because otherwise the Phase 5
  context builder could never include user-created Events or Observations.
  Keep all pre-existing entries off until the owner opts in. Preserve each
  permission change in the ordinary revision history. Implement a PostgreSQL
  full-text index for typed payloads and common envelope text, with only
  additive index migration changes. Keep delegation, provider registration,
  live safety copy, retention policy, and real-service evaluation as launch
  gates for a later supplied-contract follow-up.

## User outcome / scope

**Deliver:** an Assistant that answers using an explicit, minimized owner-scoped HealthContextPack, Health search and typed read tools. User sees what was shared and why. Optional Personal AI disabled/unavailable leaves the non-AI app fully usable.

**Defer:** canonical writes/proposals until Phase 6; derived signals/trends/insights until Phase 7; device import/records until Phases 8–9; cross-app data sharing without explicit policy/authorization; a second model/provider stack, generic DB tools, full-profile dumps, local LLM/research orchestration. Read-only means no pending proposal objects either; draft suggestion prose cannot claim “saved.”

## Health context/search contracts

Health builds context in the application layer over existing authorized read services. Personal AI has no database/object-storage credentials and does not own health facts or duplicate them into generic durable memory. Phase 1 object permission defaults are restrictive; sharing requires opt-in. Context eligibility requires owner, active/effective as_of, `ai_use_allowed`, requested scope, source confidence/confirmation and task relevance. User override can narrow scope, never expand beyond permission without explicit consent recorded in Health. Cross-domain-use permission is separate and unused by ordinary Health Assistant.

Planned `HealthContextPack` v1:

- `schema_version`, `request_id`, authorized principal scope (opaque identifier), `as_of`, timezone, requested task/risk class and allowed sections;
- constraints, applicable contexts, goals/preferences, current Profile, Today, recent Event/Observation summaries and planning items from completed phases only;
- each entry: object ID+revision, type/domain, effective/source/confirmation summary, permitted minimal content, relevance reason; aggregate sections state window/method/coverage;
- `included_counts`, `omitted_counts` and reasons, `truncated`, budget/method version; no tokens/credentials/raw object URLs;
- evidence references resolvable by owner through existing APIs, with `missing`/`stale` behavior rather than invented citations.

Do not include unimplemented trends/records/insights sections; extend the versioned contract in Phases 7/9. Rank deterministically: relevant safety constraints and active context first, then goals/preferences, task-matching facts, Today and bounded recent history. Source/confirmation and temporal relevance participate explicitly; unknown stays unknown. For relevant allergies/constraints, show uncertainty rather than dropping them because sparsity is inconvenient. Never claim context is complete. Default lookback30 days/max90 unless a bounded task explicitly requests otherwise; max100 object entries and serialized context64KB, with deterministic truncation including mandatory relevant constraints where possible. Reject request when critical requested constraints cannot fit safely rather than silently omitting them. Text/unit/time normalization uses existing domain rules. Token estimate is a budget aid, not model authority.

Planned `POST /ai/context` accepts typed task, time bounds, domains/sections and opt-in scope, returns preview Pack plus inclusion rationale. Owner resolved through established auth. `GET /search?q=...&types=...&limit=...&cursor=...` searches only current eligible Health resources with Postgres indexed filtering/FTS, q max500 characters, page20/max50 and bounded result snippet/evidence. A user-facing non-AI search may include owner data without AI permission, but any tool/context search uses stricter `ai_use_allowed`; distinguish purpose on server, never a caller-supplied bypass. Handle text as data; parameterized queries/no full SQL input. No vector service required. History is not eligible by default; archived/expired content requires explicit bounded historical task and permission.

## External tool and Assistant protocol

The exact live protocol is a **required external reconciliation gate**. Define Health-owned versioned adapter DTOs first, then map to the real Personal AI contract. Planned read capability registry: `health.context`, `health.search`, `health.today`, `health.profile`, `health.goals`, `health.plans`; no `health.trends` or `health.records` yet. Tool inputs are typed/bounded; outputs use existing DTOs/minimized Pack. Both API layer and application calls enforce allowed scopes. No table access, generic arbitrary endpoint fetch or write method.

Service-to-service identity proves Personal AI caller separately from end-user delegation. Use the actual ecosystem auth contract; the Health delegation must bind owner, request/conversation scope, allowed read capabilities, audience and short expiry. Never trust an owner ID in tool arguments. User token cannot become unrestricted reusable service credential; no forwarding bearer token to model/provider. Tool callback rechecks permissions, source revisions, ownership and expiry. Fail closed on absent/foreign/expired delegation. Bind tool completion to the current request; no cross-user global context cache. Revoking opt-in prevents subsequent tool reads.

Planned `POST /assistant/messages` accepts message≤8000 characters and reviewed context scope; Health builds the actual Pack immediately before outbound call (preview may be stale), invokes adapter and returns `{request_id, reply, risk_class, context_summary, evidence_refs, service_status}`. If external system supports conversation IDs, store/use only owner-scoped mappings; do not create a competing conversation engine. Keep context/minimal chat in memory for Phase 5 if durable Health conversation is not needed; specify external retention policy before real health use. Non-consented data must not be sent even if mentioned in unrelated cached context. Error responses sanitized: disabled/unavailable 503 code with recoverable UI, timeout bounded30s, request size/budget 422, auth/delegation 401/403 as appropriate, foreign resource404.

Personal AI text is untrusted: references must resolve to included/authorized evidence, unsupported citation marked unavailable; never execute tools/routes from free text or render raw HTML. Treat health notes/doc-like text as data to resist prompt injection; allowlisted tools and server authorization provide hard boundaries regardless of prompt wording. Set per-request max8 tool calls, time/size caps and no unbounded recursive tool loop. Check real service timeout/retry support; do not auto-repeat a sent message with unknown external outcome. Correlation/request ID permits safe retry only if provider actually supports it.

Risk classification contract: general wellness, education, consequential medical reasoning, urgent safety. Health applies deterministic conservative checks/request task tags and a floor; Personal AI may raise but never lower classification. Consequential outputs require qualified framing and grounded limitations; urgent category uses a vetted escalation UX instead of routine optimization advice. Final approved copy/classifier fixtures require implementation-time safety review against authoritative current guidance; these plans do not claim clinical validation. No diagnosis/dosing or automatic action under any class. Unknown/contradictory evidence yields explicit limitations. High-risk unsupported live policy is a launch gate, not a reason to fabricate safe-looking responses.

Mobile `src/features/assistant` adds Assistant navigation, context selector/preview and permission editing, visible included sources and bounded response/evidence cards. Explain opt-in defaults, show pending/disabled/unavailable/timeout states, preserve message draft in memory, accessible reading/focus, cancel UI with no false assurance external processing stopped. No product writes, save buttons or proposal confirmation yet. Sign-out/user switch clears context/messages from cache. Offline context preview may show last in-memory data as stale but cannot silently call AI later.

## Dependency map / packages

`P5.1 external/privacy/safety protocol -> P5.2 context/search -> P5.3 bounded read adapter/tools -> P5.4 Assistant -> P5.5 boundary evaluation`. Context fixtures and adapter fake can proceed separately after P5.1. Live activation waits for service/auth/retention/policy verification.

### P5.1 — Reconcile the live boundary and policy

**Dependencies:** Phase 4 evidence and supplied Personal AI contract. **Goal:** explicit sharing/read-only protocol.

**Areas:** AI/security/API docs, config/integrations; provisional versioned DTOs/capability registry.

**Work:** inspect real endpoint/auth/delegation/error/retention, set disabled default, define privacy eligibility/budgets, risk floors and launch gates. Document unknown external capabilities; do not implement guessed live endpoints.

**Requirements:** Health authority and no DB secrets; no generic memory competing health store. **Tests:** DTO/size/version/risk-floor/disabled-setting fixtures. **Acceptance:** fake contract executable and real integration mismatches clearly gated. **Out of scope:** model provider orchestration and actions.

### P5.2 — Implement context builder and health search

**Dependencies:** P5.1 and existing read services. **Goal:** minimized deterministic retrieval.

**Areas:** application queries/domain permissions, API schemas/routes, optional FTS indexes migration; tests/client.

**Work:** compose Pack, deterministic ranking/truncation, relevance/time/provenance, search/indexes, scope preview/permission UI contracts; use one DB snapshot and revision references.

**Requirements:** owner+AI permission checked on every included row/snippet/relationship; no unimplemented sections. **Tests:** sparse/DST/context-overlap, two-owner results, permission revocation, stale reference, mandatory constraints over budget, injection-like text and paging. **Acceptance:** golden packs match expected scope without health log leakage. **Out of scope:** trend computation/vector search.

### P5.3 — Read-only Personal AI adapter and delegated tools

**Dependencies:** P5.2; real protocol for live mapping. **Goal:** bounded service invocation.

**Areas:** integrations/api/config and test fakes; provisional assistant orchestration/callback authorization.

**Work:** typed adapter with disabled/fake/live implementations, service+user delegation, capability allowlist, deadlines/tool caps/cancellation/error sanitization; forbid write tools and credentials in output.

**Requirements:** outbound destinations configured server-side, no arbitrary user URL; fail closed; references owner-resolved. **Tests:** unavailable/timeout/malformed/oversized response, expired/foreign delegation, attempted write tool, excessive calls, stale/invented evidence. **Acceptance:** offline tests prove boundary; actual service auth/read smoke required before live enablement. **Out of scope:** proposal persistence or direct save exception.

### P5.4 — Assistant and consent UX

**Dependencies:** P5.3 generated transport contract. **Goal:** transparent optional assistance.

**Areas:** mobile app/features/tests; planned Assistant/permission scopes UI.

**Work:** preview/scope editing, read-only exchange, context/evidence display and risk/disabled/error states; preserve non-AI navigation.

**Requirements:** explicit opt-in, accessible error/focus, no hidden writes, no persistent sensitive chat logs. **Tests:** opt-out/permission-revoke/sign-out/user switch, fake response references, high-risk/urgent policy presentation, disabled/offline/draft retention. **Acceptance:** clear scope and no “saved” claim for prose suggestions. **Out of scope:** proposal buttons, research workspace/web.

### P5.5 — Evaluate privacy and service behavior

**Dependencies:** all preceding packages. **Goal:** trustworthy Phase 6 boundary.

**Areas:** synthetic evaluations/API/mobile tests, AI/security docs; provisional phase-5 evidence.

**Work:** adversarial tool/injection/owner/risk fixtures; inspect sanitized logs/network with synthetic context; run live service auth/retention/policy checks where authorized; list remaining gates.

**Requirements:** mocks never certify real service behavior, no real personal health test data required. **Tests:** repeat context golden cases and non-AI regressions, actual read-only service interaction. **Acceptance:** live disabled when required safety/privacy gates fail. **Out of scope:** claiming medically validated reasoning.

## Compatibility, failure and verification

Reuse existing permissions/context/history. Only additive permission/index/config changes; document defaults on existing rows before enabling AI. A preview isn't an authorization token to stale context: rebuild/recheck on send. Disable AI on rollback without affecting health CRUD. No canonical mutation by requests, responses, tool calls or returned instructions. OpenAPI/client regeneration accompanies new Assistant/context endpoints; external DTO adapters separate internal stable contracts from provider drift.

| Risk                         | Deterministic evidence                                         | External gate                                          |
| ---------------------------- | -------------------------------------------------------------- | ------------------------------------------------------ |
| Minimal context/time/unknown | Golden Packs/ranking/budget fixtures                           | User context review                                    |
| Ownership/permissions        | Two-owner/revocation/delegation matrix                         | Real service identity/auth                             |
| AI write boundary            | Reject every non-allowlisted tool; DB unchanged after messages | Live tool-registration audit                           |
| Safety/injection             | Conservative risk fixtures, text-as-data, invalid evidence     | Approved safety copy/policy and real service checks    |
| Optional dependency          | Disabled/timeouts/caps and non-AI regression                   | Actual provider timeout/retention/idempotency behavior |

## Acceptance / completion review / handoff

Assistant can answer using permitted bounded context with visible evidence and scope; all canonical rows/history remain unchanged by AI exchange; external outages leave manual app usable; no secret/native/web leakage. Live integration is only considered complete with actual auth/privacy/policy verification; otherwise deliver disabled mode and explicitly report unfinished external gates.

Before Phase 6: Is every outbound datum permitted and revisioned? Can a tool never escalate user/capability? Are read-only behavior and non-AI fallback proven? Are risk/policy/retention gaps visible? Is the actual provider contract documented?

Luna Max must create planned `docs/implementation/evidence/phase-5-release.md` with actual Pack/tool/assistant schemas, permissions/budgets/ranking method and fixtures, service/auth/delegation mapping, retention policy, flags/config names, generated procedure, offline/live results separately, safety policy/copy review and unverified provider gates. Phase 6 must consume this real boundary rather than redefining AI orchestration.
