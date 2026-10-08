# Current implementation state

Updated October 8, 2026. This page is the single living summary of delivered
scope, current work boundaries, and open acceptance gates. It is reconciled
from the latest code and release/review evidence through the Phase 9 local
export and domain-erasure foundation.

## Delivered locally

| Capability                                         | Current boundary                                                                                                                                                                                                                                                                                                                                                                                                                               | Evidence                                                                                                                                                                                                                                  |
| -------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Profile and canonical health records               | Owner-scoped Profile facts, provenance, revision history, and generated API client are implemented. External and device acceptance remains open.                                                                                                                                                                                                                                                                                               | [Phase 1 release](implementation/evidence/phase-1-release.md), [review](implementation/evidence/phase-1-review.md)                                                                                                                        |
| Daily state and Today                              | Typed Events/Observations, manual Add, and deterministic Today summaries/paging are implemented. The API suite runs against PostgreSQL 17 in CI; live Neon parity and production acceptance remain open.                                                                                                                                                                                                                                       | [Phase 2 release](implementation/evidence/phase-2-release.md), [review](implementation/evidence/phase-2-review.md)                                                                                                                        |
| Identity and cloud foundation                      | Firebase verification, owner mapping, private GCS/Neon configuration, and deployment artifacts exist. No live cloud deployment or parity acceptance is recorded.                                                                                                                                                                                                                                                                               | [Phase 3 release](implementation/evidence/phase-3-release.md), [review](implementation/evidence/phase-3-review.md)                                                                                                                        |
| Runtime readiness, safe logs, and CI               | `/healthz` is process liveness; `/readyz` checks the canonical database. Request events are structured JSON with bounded request IDs and operational fields only. CI checks Terraform and builds the production API image; no cloud deployment or live IAM/database acceptance is claimed.                                                                                                                                                     | [API runtime](../services/api/src/health_api/main.py), [request middleware](../services/api/src/health_api/api/middleware.py), [CI workflow](../.github/workflows/ci.yml), [Cloud Run runbook](../infra/gcp/README.md)                    |
| Planning and trackers                              | Goals, regimens, plans, active contexts, custom trackers, schedules, and occurrence history are implemented locally. PostgreSQL 17 API regressions run in CI; live Neon parity, production concurrency, cloud, and device gates remain open.                                                                                                                                                                                                   | [Phase 4 release](implementation/evidence/phase-4-release.md), [follow-up audit](implementation/evidence/phase-4-audit.md)                                                                                                                |
| Health context and search                          | Consent-scoped context preview and search are available locally. Phase 7 adds an explicitly selected trend summary over AI-permitted inputs; custom tracker entry details remain excluded from context/search results.                                                                                                                                                                                                                         | [Phase 5 release](implementation/evidence/phase-5-release.md), [Phase 7 release](implementation/evidence/phase-7-release.md)                                                                                                              |
| Typed action proposals                             | Owner-authored typed proposals can be reviewed, applied, rejected, and replayed idempotently. AI-originated proposal submission is unavailable. PostgreSQL API regressions run in CI; production concurrency and device acceptance remain open.                                                                                                                                                                                                | [Phase 6 release](implementation/evidence/phase-6-release.md), [initial review findings](implementation/evidence/phase-6-independent-review-initial.md), [ADR 0006](architecture/adr/0006-ai-mutation-proposals.md)                       |
| Trends, insights, recommendations, and experiments | Deterministic bounded analysis, exact revision evidence, expiring insight/recommendation history, manual experiments, and mobile Insights/Today surfaces are implemented locally. The PostgreSQL 17 API suite runs in CI; complete numerical goldens, full AI permission/`as_of` integration coverage, unrepresented race cases, query-plan measurements, and device walkthrough remain open.                                                  | [Phase 7 release](implementation/evidence/phase-7-release.md), [Phase 7 plan](implementation/phases/phase-7-implementation-plan.md)                                                                                                       |
| Selective HealthKit import foundation              | Owner-scoped batch contract, source identities/preferences/revisions, normalized mobile mappings, secure per-account consent/checkpoints, and review fixes are implemented locally. PostgreSQL-backed API tests run in CI; Neon parity, production concurrency, and device acceptance remain open. The native adapter stays unavailable pending a compatible iOS build and real-device verification.                                           | [Phase 8 release](implementation/evidence/phase-8-release.md), [independent review](implementation/evidence/phase-8-independent-review.md), [Phase 8 plan](implementation/phases/phase-8-implementation-plan.md)                          |
| Owner export and domain erasure foundation         | Repeatable-read owner JSON export, explicit/recent-auth domain deletion, owner write freeze, bounded private-object cleanup, dependency-ordered erasure, and a health-free erasure marker are implemented locally. Historical Phase 9 PostgreSQL 16.15 and 17.11 tests cover every inventory table and export/erasure recovery. The marker has no restore-replay runner; live cloud, object, device, and restore-drill acceptance remain open. | [Phase 9 release evidence](implementation/evidence/phase-9-release.md), [independent review and remediation](implementation/evidence/phase-9-independent-review.md), [Phase 9 plan](implementation/phases/phase-9-implementation-plan.md) |

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
- Local Health context preview and search work without Personal AI. The
  `AIContextPack` is a local preview response, not a cross-service transport
  contract. `/assistant/status` reports disabled with no capabilities, and
  `/assistant/messages` always returns a sanitized 503 without building
  context or invoking an adapter. `PERSONAL_AI_ENABLED=true` remains rejected.
- Personal AI's typed provider/planner/builder architecture is documented as
  the intended shared integration boundary. Health Phase 29 provider
  registration, delegated owner authorization, retention/privacy review, and
  live safety acceptance are not implemented; canonical health state remains
  owned by Health. See the [boundary alignment evidence](implementation/evidence/personal-ai-boundary-alignment-2026-10-08.md).
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

- GitHub Actions provisions PostgreSQL 17 for the API job, and the test fixture
  upgrades Alembic to head before running the full API suite. This gives the
  repository automated PostgreSQL 17 migration/API regression coverage for the
  tests that execute in that suite. The Phase 9 release record is historical:
  it documents local PostgreSQL 16.15 and 17.11 verification for migration
  drift, owner-table export/erasure, isolation, snapshot consistency, write
  freeze, recovery, and downgrade refusal. These checks do not establish live
  Neon parity, production concurrency, or race conditions the suite does not
  represent. See the [CI workflow](../.github/workflows/ci.yml),
  [PostgreSQL test fixture](../services/api/tests/conftest.py), and
  [Phase 9 release evidence](implementation/evidence/phase-9-release.md).
- Live Neon networking/pooling, production concurrency under realistic load,
  unrepresented races, broader query-plan/performance measurements, live
  Firebase/GCS/Cloud Run identity and IAM behavior, backup/restore, deletion
  replay, and measured RPO/RTO remain open.
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
  real-device reads/deletes for every enabled type. PostgreSQL-backed API tests
  run in CI; Neon parity and production concurrency remain open. See the Phase
  8 release record for native and device gates.
- Phase 7 now has focused snapshot, linked-severity, tracker-label, and
  experiment-boundary regression fixtures. The complete numerical goldens,
  full AI permission/`as_of` integration coverage, race cases not represented
  by current tests, query-plan measurements, and device walkthrough remain
  open; see its release record.
- Live cloud deployment, Firebase/GCS permissions, storage/database parity,
  backup/restore, and cost checks have not been established.
- Device review remains open for accessibility, keyboard interaction,
  timezone behavior, session/account changes, and proposal confirmation.
- The Health Application Integration Contract, retention/privacy review,
  delegated-owner authorization, live read-only safety evaluation, and
  provider behavior are unverified; live messaging remains disabled.
- Earlier dependency advisory/source-use review gates are still listed in
  Phase 1 evidence.

See each linked release record for exact commands, results, skipped database
checks, dated deviations, and external gates. Do not infer acceptance from
source presence or a plan.

## Current scope

Phase 8's normalized import foundation and independent-review fixes are
implemented locally; its release evidence records historical checks and open
native/device gates. The current CI workflow provisions PostgreSQL 17 and runs
the API tests after Alembic upgrades to head. Phase 9 adds the local export and
domain-erasure foundation, including HealthKit import identity/receipt cleanup;
its release evidence records local PostgreSQL 16.15 and 17.11 runs. Client-side
consent/checkpoint clearing is covered by mobile tests but needs device
verification. The record lifecycle still needs implementation and verification
before document ingress can be enabled.

## High-context code areas

- services/api/src/health_api/application/ai_context_service.py is the stable
  local preview/search façade. ai_context_admission.py owns the SQL eligibility
  gate; ai_context_projection.py owns relationship-safe local fields;
  ai_context_ranking.py and ai_context_search.py own full-text ranking and
  search pagination; ai_context_pack.py owns Today/trend assembly and response
  budgets.
- services/api/src/health_api/application/analytics_service.py is the stable
  route-facing façade. analytics_sources.py loads bounded owner snapshots and
  generation markers; analytics_computation.py derives deterministic points
  from typed snapshots; analytics_artifacts.py owns evidence-linked
  persistence, lifecycle, and pre-commit generation/evidence revalidation.
- services/api/src/health_api/application/action_proposal_service.py is the
  stable proposal façade. proposal_lifecycle.py owns proposal revisions and
  lifecycle; proposal_validation.py owns command/evidence validation and
  preview; proposal_apply.py owns exact confirmation, transaction locks,
  execution, receipts, and replay. proposal_support.py owns shared snapshots
  and review-state helpers.
- services/api/src/health_api/application/planning_service.py is the stable
  planning façade. planning_resources.py owns resource/history operations,
  planning_schedules.py owns schedules and occurrences, and
  planning_trackers.py owns tracker schema history and custom-entry
  validation. These paths combine immutable revisions, timezones, recurrence,
  and actual-log relationships; see the domain and application READMEs before
  changing them.
