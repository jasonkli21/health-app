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
- A separate default-off
  `POST /v1/integrations/personal-ai/federation-export` supports only dietary
  restrictions → Travel and ergonomic constraints → Shopping. It requires the
  Personal AI service identity plus a short-lived Ed25519-signed delegated
  Google identity assertion bound to Health's audience, recent-auth time, exact
  request body, purpose, and destination. Health resolves the Google subject to
  an already-linked Firebase provider and then resolves its existing Firebase
  owner; it still rechecks Health-owned consent, object status, revision, and
  sensitivity before returning data. The assertion is request-only and is not
  stored with the grant, context snapshot, logs, or proposal metadata.

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

The Health read gate defaults off and does not alter `/assistant/status` or
`/assistant/messages`. Owners can set daily `cross_domain_use_allowed` during
create and update; the mobile daily-entry form exposes this default-off choice
for both new and existing entries. Those writes advance the canonical object
revision and append a history snapshot containing the permission state. Health
context dependency versions include that revision and both Health consent
values, so a regrant creates a new version. The consent records a Health-owned
prerequisite and does not activate the still-disabled Personal AI integration.
Health's local `ai_use_allowed` and
`cross_domain_use_allowed` are source-domain prerequisites. A future Phase 30
federation grant is an additional authorization; effective access is their
intersection, with separate dependency versions.

The broader Phase 29 context-read endpoint still requires a recent Firebase
token and remains unavailable to Personal AI's Google OIDC adapter. Phase 30's
narrow export uses the separate signed assertion bridge described above. Its
default-off gate, linked-account dependency, PostgreSQL-backed export tests,
cloud IAM, deployed identity/privacy review, and the Shopping destination
chooser/host remain open. Travel's local host now exposes the generic chooser;
these remaining items are activation gaps, not passed external checks.

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
