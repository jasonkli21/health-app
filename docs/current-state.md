# Current implementation state

Updated October 7, 2026. This page is the single living summary of delivered
scope, current work boundaries, and open acceptance gates. It is reconciled
from the latest code and release/review evidence through the Phase 9 local
export and domain-erasure foundation.

## Delivered locally

| Capability                                         | Current boundary                                                                                                                                                                                                                                                                                                                                                                                                  | Evidence                                                                                                                                                                                                                                  |
| -------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Profile and canonical health records               | Owner-scoped Profile facts, provenance, revision history, and generated API client are implemented. External and device acceptance remains open.                                                                                                                                                                                                                                                                  | [Phase 1 release](implementation/evidence/phase-1-release.md), [review](implementation/evidence/phase-1-review.md)                                                                                                                        |
| Daily state and Today                              | Typed Events/Observations, manual Add, and deterministic Today summaries/paging are implemented. PostgreSQL integration acceptance remains open.                                                                                                                                                                                                                                                                  | [Phase 2 release](implementation/evidence/phase-2-release.md), [review](implementation/evidence/phase-2-review.md)                                                                                                                        |
| Identity and cloud foundation                      | Firebase verification, owner mapping, private GCS/Neon configuration, and deployment artifacts exist. No live cloud deployment or parity acceptance is recorded.                                                                                                                                                                                                                                                  | [Phase 3 release](implementation/evidence/phase-3-release.md), [review](implementation/evidence/phase-3-review.md)                                                                                                                        |
| Planning and trackers                              | Goals, regimens, plans, active contexts, custom trackers, schedules, and occurrence history are implemented locally. Database, cloud, and device gates remain open.                                                                                                                                                                                                                                               | [Phase 4 release](implementation/evidence/phase-4-release.md), [follow-up audit](implementation/evidence/phase-4-audit.md)                                                                                                                |
| Health context and search                          | Consent-scoped context preview and search are available locally. Phase 7 adds an explicitly selected trend summary over AI-permitted inputs; custom tracker entry details remain excluded from context/search results.                                                                                                                                                                                            | [Phase 5 release](implementation/evidence/phase-5-release.md), [Phase 7 release](implementation/evidence/phase-7-release.md)                                                                                                              |
| Typed action proposals                             | Owner-authored typed proposals can be reviewed, applied, rejected, and replayed idempotently. AI-originated proposal submission is unavailable. PostgreSQL concurrency and device acceptance remain open.                                                                                                                                                                                                         | [Phase 6 release](implementation/evidence/phase-6-release.md), [initial review findings](implementation/evidence/phase-6-independent-review-initial.md), [ADR 0006](architecture/adr/0006-ai-mutation-proposals.md)                       |
| Trends, insights, recommendations, and experiments | Deterministic bounded analysis, exact revision evidence, expiring insight/recommendation history, manual experiments, and mobile Insights/Today surfaces are implemented locally. Automated and PostgreSQL-backed Phase 7 acceptance remains open.                                                                                                                                                                | [Phase 7 release](implementation/evidence/phase-7-release.md), [Phase 7 plan](implementation/phases/phase-7-implementation-plan.md)                                                                                                       |
| Selective HealthKit import foundation              | Owner-scoped batch contract, source identities/preferences/revisions, normalized mobile mappings, secure per-account consent/checkpoints, and review fixes are implemented locally. The native adapter stays unavailable pending a compatible iOS build and real-device verification; PostgreSQL acceptance also remains open.                                                                                    | [Phase 8 release](implementation/evidence/phase-8-release.md), [independent review](implementation/evidence/phase-8-independent-review.md), [Phase 8 plan](implementation/phases/phase-8-implementation-plan.md)                          |
| Owner export and domain erasure foundation         | Repeatable-read owner JSON export, explicit/recent-auth domain deletion, owner write freeze, bounded private-object cleanup, dependency-ordered erasure, and a health-free erasure marker are implemented locally. PostgreSQL 16.15 tests cover every inventory table and export/erasure recovery. The marker has no restore-replay runner; live cloud, object, device, and restore-drill acceptance remain open. | [Phase 9 release evidence](implementation/evidence/phase-9-release.md), [independent review and remediation](implementation/evidence/phase-9-independent-review.md), [Phase 9 plan](implementation/phases/phase-9-implementation-plan.md) |

Phase 9 document records, reviewed extraction and Records review surfaces,
durable large exports, backup/restore, and whole-system maturity are not
delivered. Phase 8 source delivery does not establish clinical validity, live
database behavior, HealthKit permission or query behavior, or device
accessibility.

## AI, authorization, and private data

- The Health app owns canonical health state. Personal AI is an external,
  optional reasoning capability and has no database credentials.
- Context and search recheck owner, active/current status, time validity, and
  item-level AI permission. Permission defaults to off; request scope may
  narrow sharing but cannot grant permission.
- Local Assistant preview and search work without a provider. Live messages
  are disabled: no provider endpoint, service identity, user-delegation,
  callback, or retention contract has been supplied. No live AI or clinical
  safety acceptance is claimed.
- Proposal apply requires the exact reviewed revision/hash and explicit
  confirmation. General AI-originated writes remain unavailable.
- Cloud auth and private-storage boundaries are implemented in code, but live
  cloud identity, Neon/GCS parity, deployment, and restore checks remain
  unverified. Require verified auth and private cloud storage before real
  sensitive ingress. Routine fixtures and logs use no real health payloads.

## Mobile and web boundary

The product is mobile-first with Expo/React Native and a shared generated API
client. No web client is implemented. HealthKit mappings and sync coordination
stay behind mobile-specific adapters; this build has no verified native
HealthKit adapter and does not request Apple permissions or start a sync. Web
architecture documents are routed only for web/shared-client work.

## Open acceptance gates

- PostgreSQL 16.15 verification now covers the Phase 9 migration upgrade and
  drift check, full owner-table export/erasure, owner isolation, concurrent
  snapshot consistency, write freeze, same-request recovery, and downgrade
  refusal. PostgreSQL 17, Neon parity, broader cross-phase query plans, and
  production concurrency remain open.
- GCS cleanup tests use a fake adapter and cover bounded batches, timeouts,
  generation checks, and retries. Live GCS behavior, backup policy, isolated
  restore, deletion replay, and measured RPO/RTO remain unverified.
- The mobile deletion screen clears the current account's indexed secure
  consent/checkpoint entries after server completion, but no native HealthKit
  adapter currently writes checkpoints. Real-device/account-switch behavior
  remains unverified.
- Record upload and lab extraction remain disabled: no malware scanner or
  isolated parser policy is configured, and no approved Personal AI extraction
  protocol/retention contract exists.
- Phase 8 still needs a compatible iOS development build, a selected and
  verified native HealthKit library, entitlement and permission behavior, and
  real-device reads/deletes for every enabled type. The transactional import
  API and preference behavior also need PostgreSQL-backed migration and
  concurrency verification; see the Phase 8 release record.
- Phase 7 now has focused snapshot, linked-severity, tracker-label, and
  experiment-boundary regression fixtures. The complete numerical goldens,
  AI permission/`as_of` integration coverage, PostgreSQL invalidation and race
  tests, query-plan measurements, and device walkthrough remain open; see its
  release record.
- Live cloud deployment, Firebase/GCS permissions, storage/database parity,
  backup/restore, and cost checks have not been established.
- Device review remains open for accessibility, keyboard interaction,
  timezone behavior, session/account changes, and proposal confirmation.
- The real Personal AI contract, retention/privacy review, delegated-owner
  authorization, live read-only safety evaluation, and provider behavior are
  unverified; the adapter remains disabled.
- Earlier dependency advisory/source-use review gates are still listed in
  Phase 1 evidence.

See each linked release record for exact commands, results, skipped database
checks, dated deviations, and external gates. Do not infer acceptance from
source presence or a plan.

## Current scope

Phase 8's normalized import foundation and independent-review fixes are
implemented locally; its release evidence records the verified checks and
open native/database acceptance gates. Phase 9 now adds the local export and
domain-erasure foundation, including HealthKit import identity/receipt cleanup.
The Phase 9 migration and owner-data behavior pass the local PostgreSQL 16.15
suite. Client-side consent/checkpoint clearing is covered by mobile tests but
needs device verification. The record lifecycle still needs implementation
and verification before document ingress can be enabled.

## High-context code areas

- services/api/src/health_api/application/ai_context_service.py owns
  consent filtering, relationship-safe context/search, deterministic ranking,
  and bounded response assembly.
- services/api/src/health_api/application/action_proposal_service.py owns
  proposal revisioning, validation, transactional apply, and replay receipts.
- Planning schedules and Today combine recurrence, immutable revisions,
  timezones, and actual-log relationships. See the domain and application
  READMEs before changing these paths.
