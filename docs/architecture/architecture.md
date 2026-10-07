# System architecture

## Ownership boundary

The Health application owns canonical health state, domain validation, health-specific retrieval, analytics, and actions. Personal AI is the intended owner of model/provider orchestration, general conversation/memory, research/search, and cross-domain reasoning.

```text
Mobile Health UI
      |
      v
Health API -- reviewed, scoped contract --> Personal AI System
   |                                |
   v                                v
Postgres <--------------------- Health API
   |
   +--> object storage references
```

The Personal AI System never connects directly to the Health database.

## Local architecture

Expo app, FastAPI localhost, PostgreSQL Docker, and local objects. Ordinary development works without cloud. Provider messaging stays disabled until its external contract is reviewed.

## Cloud architecture

Target topology: Expo client, shared auth, Cloud Run Health API, isolated Neon Postgres, private GCS, and an authenticated Personal AI service. This is a design target, not a deployed environment; see current state.

## Layering

`api`, `application`, `domain`, `persistence`, `integrations`, `config`. Route handlers remain thin.

## Integration philosophy

HealthKit and future wearable/provider integrations normalize into Event/Observation/source. High-frequency raw device data is not mirrored wholesale.

## Future web client

After the mobile/backend Phase 0–9 roadmap is complete, a Next.js web client can be added as another presentation layer over the same Health API. Shared code should center on generated contracts, frontend-safe domain utilities, and design tokens. HealthKit/native dependencies must remain mobile-only.

## Infrastructure intentionally absent initially

No Redis, Pub/Sub, Kafka, Elasticsearch, external vector DB, time-series DB, or separate warehouse without demonstrated need.
