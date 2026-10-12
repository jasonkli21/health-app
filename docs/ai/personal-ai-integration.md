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
- `GET /assistant/status` remains authenticated and reports disabled with no
  capabilities. `POST /assistant/messages` remains available for client
  compatibility and always returns a sanitized 503.
- A separate `POST /v1/integrations/personal-ai/context` implements the
  versioned `health-context-read-v1` read contract. Its default-off
  `PERSONAL_AI_CONTEXT_READ_ENABLED` gate does not enable Assistant messaging.
  `PERSONAL_AI_ENABLED` still defaults to false and settings reject `true`.

## Shared architecture in Personal AI

Personal AI has a shared Application Integration Contract composed from typed
request scope, registered application capabilities, and domain-owned
adapters. Its current implementation includes registered typed context
providers and bounded operations, permission dependencies, field-level
sensitivity metadata, deterministic planning before retrieval, and a shared
context builder. Provider registration does not grant permission. Personal
AI's own current-state record still lists incomplete policy-version references
and end-to-end revocation work; this is not evidence of a Health integration.

## Local Phase 29 read contract

The contract supports authorized category catalog, profile, bounded history,
measurement time-series, and permission-revalidation reads for profile
background/constraints/preferences, measurements, nutrition, exercise, sleep,
and symptoms. Health derives the owner only from an existing exact
`(Firebase issuer, subject)` mapping. A Google service ID token with the
configured audience and exact service-account email authenticates Personal AI;
a separate recent Firebase ID token is verified with revocation checking
before any owner lookup or data query. Requests contain no owner credential.

Health returns only typed selected fields with source/object revisions,
provenance, authority, time, units, quality/unknown uncertainty, field
sensitivity, and permission dependencies. Health uses its shared
`_eligibility_conditions` gate and requires both local `ai_use_allowed` and
cross-domain `cross_domain_use_allowed`; the catalog checks eligibility before
offering categories. The response is bounded to 90 days, 32 rows, and 32 KiB.
The projection is not `AIContextPack`, stores no duplicate state, and has no
write or proposal operation. Custom tracker observations remain excluded.

The Health read gate defaults off and does not alter `/assistant/status`,
`/assistant/messages`, or Health mutation behavior. The current Personal AI
adapter can provide a Google OIDC user token, while Health requires a recent
Firebase token; there is no delegated Firebase-token bridge or live read path
between the repositories yet. Daily Health entries also default their
cross-domain permission off without an owner-facing control. The category
sidecar, identity/privacy review, cloud IAM and provider verification remain
open. These are explicit activation gaps, not passed external checks.

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

The cross-service provider projection uses server-derived scope and explicit
purpose, authorizes before fetch, returns bounded typed fields, preserves
provenance and temporal semantics, applies restricted sensitivity, denies
ungranted access, and keeps canonical Health state in Health.

See [current state](../current-state.md), the
[Health API contract](../api/api-contract.md),
[Phase 29 evidence](../implementation/evidence/phase-29-personal-ai-context.md),
[boundary alignment evidence](../implementation/evidence/personal-ai-boundary-alignment-2026-10-08.md),
and [Phase 5 release evidence](../implementation/evidence/phase-5-release.md)
for the delivered local preview/search behavior and the remaining external
gates.
