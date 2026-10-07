# ADR 0006 — AI-originated mutations use proposals

- **Status:** Accepted
- **Original decision:** General Assistant-derived health-state changes create
  typed proposals for user review; explicit form saves may commit directly.
- **Reconciled:** October 5, 2026, before Phase 6 implementation.

## Context

Phase 5 delivered a Health-owned read-only Assistant boundary, but its provider
adapter remains disabled. The repository has no Personal AI endpoint, service
identity, end-user delegation, proposal tool callback, or retention contract.
The canonical `health_objects` envelope represents health facts, while pending
proposal revisions have a distinct lifecycle and must not appear as facts.
Existing Profile, daily, and planning command services validate writes and
history but currently own their transactions and hard-code manual provenance.

## Decision

- Store pending proposals and their immutable content revisions in dedicated,
  owner-scoped proposal tables. Store append-only lifecycle events and
  idempotent command receipts separately. Do not add pending proposals to
  `health_objects`.
- Apply approved typed commands through the existing Profile, daily, and
  planning application commands within one shared database transaction. Those
  commands remain the authority for schema and owner-reference validation.
- Keep the verified owner as actor and explicit confirmer. When a proposal is
  eventually submitted by a reviewed AI adapter, preserve AI source metadata
  and `user_confirmed` status on applied objects; target history records the
  proposal ID. A proposal edit appends a new immutable revision and invalidates
  confirmation of the previous revision.
- Do not implement or enable a `health.propose.*` provider tool without the
  actual service identity, delegated-user capability, callback, and retention
  contract. Until then live provider messaging and AI-originated proposal
  submission remain disabled. Health-side preview/search and owner-authored
  proposal workflows are local capabilities. A fake adapter may test DTO
  mapping but cannot establish provider authorization.
- A deliberate Save in a structured form can confirm the displayed proposal
  revision directly through the same executor. General Assistant proposals
  still require a pending state and a separate explicit user confirmation.

## Consequences

- Proposal state, revision snapshots, event history, and receipts do not
  contaminate canonical health resource queries or search.
- Existing commands need a transaction-composition path and provenance
  parameters so the proposal executor can reuse validation without nested
  commits or relabeling AI origin as manual.
- Migrations, command receipts, proposal audit events, and target histories
  must commit or roll back together. Feature disablement blocks new proposal
  submission but must leave existing proposals readable and rejectable.
- Phase 6 local implementation cannot claim live AI submission or live
  provider authorization until the external boundary is supplied and reviewed.
