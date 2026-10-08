# Personal AI integration

Health owns canonical health state, authorization, validation, and health
mutations. Personal AI is an optional reasoning service and has no Health
database credentials. The current Health boundary is local preview/search plus
an explicitly disabled live-message route.

## Implemented in Health now

- `POST /ai/context` returns a bounded, owner-scoped Health preview. Each
  request rechecks item-level AI permission, active state, temporal validity,
  and requested narrowing.
- `GET /search` searches only current owner resources explicitly allowed for AI
  use. These are Health-owned local features and do not require Personal AI.
- Owners can review and apply typed action proposals through Health's explicit
  proposal flow. Personal AI cannot submit proposals or write canonical state.
- `GET /assistant/status` is authenticated and reports the live integration as
  disabled with no capabilities. `POST /assistant/messages` remains available
  for client compatibility and always returns a sanitized 503 until the
  Personal AI Application Integration Contract is implemented and reviewed.
- `PERSONAL_AI_ENABLED` defaults to false, and settings reject `true`. No
  endpoint, service credential, delegated-owner token, or callback is
  configured.

## Shared architecture in Personal AI

Personal AI has a shared Application Integration Contract composed from typed
request scope, registered application capabilities, and domain-owned
adapters. Its current implementation includes registered typed context
providers and bounded operations, permission dependencies, field-level
sensitivity metadata, deterministic planning before retrieval, and a shared
context builder. Provider registration does not grant permission. Personal
AI's own current-state record still lists incomplete policy-version references
and end-to-end revocation work; this is not evidence of a Health integration.

## Planned Health read integration

Personal AI Phase 29 plans for Health to expose Health-owned, read-only typed
capabilities through the Application Integration Contract. Health must
authorize an owner, application/workspace scope, purpose, category, and
operation before fetching that category. Responses must be bounded and
domain-typed, preserving source identity/version, provenance and authority,
effective/source time, units, uncertainty, and field-level sensitivity. The
most restrictive sensitivity must apply downstream. Cross-app Health use is
denied by default unless explicitly authorized. An owner identifier inside a
payload is not authorization, and verbose sensitive artifacts should be kept
to a minimum or disabled.

No Phase 29 provider endpoint, registration, or live Health integration is
implemented here. The local preview remains a separate Health capability.

## Planned mutation integration

Personal AI Phase 31 describes typed mutation proposals. Generic orchestration
may own proposal metadata and workflow, while Health remains responsible for
owner authorization, domain validation, the authoritative write, and the
returned post-state. Health may reject sensitive operations even when a
generic proposal has user confirmation. The current Health proposal flow is
owner-authored; AI-originated proposal submission remains unavailable.

## Local preview is not the interchange contract

`AIContextPack` is a response model for an authenticated local Health preview.
It contains Health-specific fields, including a generic JSON `content` value,
and does not carry the future provider contract's complete field sensitivity
and permission-dependency envelope. Its `owner_scope` value is not an
authorization credential. Do not send this model directly to Personal AI or
treat it as the future cross-service transport format.

A future provider projection must use server-derived scope and explicit
purpose, authorize before fetch, return bounded typed fields, preserve
provenance and temporal semantics, apply the most restrictive sensitivity,
deny cross-app use by default, and keep canonical Health state in Health.

See [current state](../current-state.md), the
[Health API contract](../api/api-contract.md),
[boundary alignment evidence](../implementation/evidence/personal-ai-boundary-alignment-2026-10-08.md),
and [Phase 5 release evidence](../implementation/evidence/phase-5-release.md)
for the delivered local preview/search behavior and the remaining external
gates.
