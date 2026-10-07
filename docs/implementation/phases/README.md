# Phase implementation plans

These plans define intended scope and sequencing. They are not delivery
evidence or authorization to begin work. Check [current state](../../current-state.md)
for implementation status and open gates, then reconcile the selected plan
against the current repository, preceding release evidence, and accepted
decisions before coding.

The [roadmap](../implementation-plan.md) sets phase order. The reusable
[plan authoring standard](../../handoff/phase-plan-authoring-standard.md)
describes how to create or materially revise a plan.

| Order | Plan                                                                 | Intended capability                                                     |
| ----- | -------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| 1     | [Canonical health model and Profile](phase-1-implementation-plan.md) | Ownership, versioned schemas, history, Profile, and generated contracts |
| 2     | [Daily health data](phase-2-implementation-plan.md)                  | Events/Observations, manual Add, Today, and deterministic rollups       |
| 3     | [Cloud baseline](phase-3-implementation-plan.md)                     | Verified identity and portable Neon/Cloud Run/GCS deployment            |
| 4     | [Personal planning](phase-4-implementation-plan.md)                  | Goals, regimens, plans, contexts, trackers, and schedules               |
| 5     | [Read-only Personal AI](phase-5-implementation-plan.md)              | Minimized context, search, and Assistant boundary                       |
| 6     | [AI action proposals](phase-6-implementation-plan.md)                | Typed, reviewed, transactional, idempotent mutations                    |
| 7     | [Insights and recommendations](phase-7-implementation-plan.md)       | Evidence-linked analytics, recommendations, and experiments             |
| 8     | [Selective HealthKit](phase-8-implementation-plan.md)                | Mobile-only native adapter and bounded source-aware imports             |
| 9     | [Records and hardening](phase-9-implementation-plan.md)              | Records, reviewed extraction, export/deletion, and end-to-end hardening |

Delivery status belongs in [current state](../../current-state.md) and dated
records in [implementation evidence](../evidence/). Future web work is routed
separately through the web architecture and plan; it is not part of this phase
sequence.
