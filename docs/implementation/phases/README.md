# Phase 1–9 implementation plans

These **planned, documentation-only** execution plans are intended for Luna Max. The [primary roadmap](../implementation-plan.md), [CODEX instructions](../../../CODEX.md), accepted ADRs, and [authoring standard](../../handoff/phase-plan-authoring-standard.md) govern scope. See the [Phase 0 review](../../handoff/phase-0-review.md) for the verified baseline and unavailable checks.

Implement sequentially; every phase depends on completed preceding phases and their evidence. Immediately before coding, inspect the entire current repository, preceding release evidence, accepted contracts/ADRs and external integration availability. Reconcile paths, migrations, schemas, commands, tests and UX. Update material design decisions before code; never force a stale planned artifact into an evolved repository. Every new path, table, route and DTO in these plans is **planned/provisional**, unless expressly identified as a Phase 0 artifact. No release evidence is being claimed for Phases 1–9.

| Order | Plan                                                                 | Capability established / next dependency                                     |
| ----- | -------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| 1     | [Canonical health model and Profile](phase-1-implementation-plan.md) | Ownership, versioned schemas, history, Profile, generated contracts          |
| 2     | [Daily health data](phase-2-implementation-plan.md)                  | Events/Observations, manual Add, Today and deterministic rollups             |
| 3     | [Cloud baseline](phase-3-implementation-plan.md)                     | Real identity/owner enforcement, portable Neon/Cloud Run/GCS deployment      |
| 4     | [Personal planning](phase-4-implementation-plan.md)                  | Goals, regimens, plans, contexts, trackers and schedules                     |
| 5     | [Read-only Personal AI](phase-5-implementation-plan.md)              | Minimized context/search, typed read tools and Assistant                     |
| 6     | [AI action proposals](phase-6-implementation-plan.md)                | Reviewed, typed, transactional, idempotent mutations                         |
| 7     | [Insights and recommendations](phase-7-implementation-plan.md)       | Evidence-linked deterministic analytics and experiments                      |
| 8     | [Selective HealthKit](phase-8-implementation-plan.md)                | Mobile native adapter, bounded retention, source-aware import                |
| 9     | [Records and hardening](phase-9-implementation-plan.md)              | Records/extraction review, export/deletion/backup, audited end-to-end system |

Cross-phase contract spine: Health owns all canonical data and validation; Personal AI has typed delegated access and no DB credentials. `health_objects` identities and revisions remain stable. History records who/what changed data and when; evidence references revisions, not floating values. Unknown differs from zero/false. Owner scoping includes joins, histories, evidence and storage. Server-generated OpenAPI owns client DTOs. Tests stay outside production source. Native imports stay in mobile. No web client, forced component reuse, vector service, event bus, Redis or new AI provider stack is required.

Phase 1 creates foundational object/history/source/relationship contracts; Phase 2 owns Events/Observations/Today. Phase 4 extends Today with schedules, Phase 7 with evidence cards, Phase 8 with imports. Phase 5 context/search includes only available resource types; Phase 9 adds records. Phase 6 owns proposal application; Phase 7 recommendations and Phase 9 extraction reuse it. Phase 3 wires storage without document/product routes. Phase 8 has no wholesale device mirror or record ingestion. Phase 9 deletion supersedes earlier logical archives through an explicit privacy workflow.

Release evidence is to be created **by the implementing session** under planned `docs/implementation/evidence/phase-N-release.md`, with actual migrations/routes/client generation, config, command results, external checks and known limits. Failed/unverified real-provider checks must stay labeled; mocks cannot certify them. Future web remains deferred after Phase 9; do not author W0–W9 detailed files here.
