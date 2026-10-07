# Documentation router

This is the first documentation stop for agents. For an ordinary task, read
[current state](current-state.md), then follow only the route that applies.
The product brief describes intent; plans describe future or phase-specific
scope; release and review records describe what was implemented and checked.

## Authority and status

When documents disagree, follow this order:

1. Current code, executable schemas/contracts, migrations, and tests.
2. Release, review, and verification evidence.
3. Accepted ADRs and decision records.
4. Product, architecture, data, security, and deployment intent.
5. Active implementation plans.
6. Historical or superseded documents.

Implementation plans do not prove delivery. Use docs/current-state.md and the
linked evidence for delivery status and open gates. Files under history are
context only.

## Route by task

| Task                                                              | Start here                                                                                                                                                                                                                                                                       |
| ----------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Product scope and user experience                                 | [Product brief](project-brief.md), [UX design](ux/ux-design.md), then [current state](current-state.md) for delivered boundaries                                                                                                                                                 |
| Health data model, time, provenance, and invariants               | [Data model](data/data-model.md), [domain README](../services/api/src/health_api/domain/README.md), relevant [ADRs](architecture/adr/) and migrations                                                                                                                            |
| API behavior, OpenAPI, or client generation                       | [API contract](api/api-contract.md), [OpenAPI contract](../contracts/openapi/README.md), and the generated API client package                                                                                                                                                    |
| Personal AI context, search, or Assistant                         | [AI integration boundary](ai/personal-ai-integration.md), [application README](../services/api/src/health_api/application/README.md), [Phase 5 evidence](implementation/evidence/phase-5-release.md), and [Phase 5 plan](implementation/phases/phase-5-implementation-plan.md)   |
| Proposal review and health mutations                              | [ADR 0006](architecture/adr/0006-ai-mutation-proposals.md), [application README](../services/api/src/health_api/application/README.md), [Phase 6 evidence](implementation/evidence/phase-6-release.md), and [Phase 6 plan](implementation/phases/phase-6-implementation-plan.md) |
| Trends, evidence-linked insights, recommendations, or experiments | [Phase 7 plan](implementation/phases/phase-7-implementation-plan.md), [Phase 7 release evidence](implementation/evidence/phase-7-release.md), [API contract](api/api-contract.md), and the domain/application/persistence READMEs                                                |
| Authentication, authorization, and privacy                        | [Security baseline](security/security-privacy.md), [integration notes](../services/api/src/health_api/integrations/README.md), and [Phase 3 evidence](implementation/evidence/phase-3-release.md)                                                                                |
| Private objects and storage                                       | [Deployment guide](deployment/technology-deployment.md), [integration notes](../services/api/src/health_api/integrations/README.md), object-storage implementation, and Phase 3/9 evidence or plans as relevant                                                                  |
| Migrations and persistence                                        | [Data model](data/data-model.md), [persistence README](../services/api/src/health_api/persistence/README.md), [migration guide](../migrations/README.md), and the relevant phase evidence                                                                                        |
| Mobile app or native integrations                                 | Current mobile code and [mobile-first ADR](architecture/adr/0003-mobile-first-expo.md); read the [HealthKit plan](implementation/phases/phase-8-implementation-plan.md) only for native import work                                                                              |
| Future web client or shared frontend boundaries                   | [Web architecture](web/web-extension-architecture.md) and [web plan](implementation/web-extension-plan.md). This context is deferred and is not needed for ordinary mobile or backend work.                                                                                      |
| Cloud deployment                                                  | [Deployment guide](deployment/technology-deployment.md), [GCP infrastructure README](../infra/gcp/README.md), and [Phase 3 evidence](implementation/evidence/phase-3-release.md)                                                                                                 |
| Active phase implementation                                       | [Current state](current-state.md), then the relevant phase plan, preceding release/review evidence, and accepted ADRs. Confirm authorization and reconcile before coding.                                                                                                        |
| Review, release, or verification history                          | [Implementation evidence](implementation/evidence/), routed from the relevant row above                                                                                                                                                                                          |

## Stable architecture references

- [Architecture overview](architecture/architecture.md)
- [Accepted decisions](architecture/adr/)
- [Security and privacy](security/security-privacy.md)
- [Local development](local-development.md)
- [Implementation roadmap](implementation/implementation-plan.md)
- [Phase plan index](implementation/phases/README.md)

The roadmap and plans describe intended work. The evidence records describe
the checks actually run and their limits.
