# Technology and deployment architecture

## Mobile

React Native + Expo + TypeScript + Expo Router. iOS first-class; use development builds for native HealthKit.

## Backend

Python + FastAPI + Pydantic; SQLAlchemy 2 + Alembic.

## Data

PostgreSQL locally, isolated Neon Postgres in cloud, local files/GCS documents. Do not mirror all high-frequency HealthKit samples.

## Compute

Cloud Run for API; Cloud Run Jobs only for genuinely long work. No Pub/Sub until needed.

## Authentication

Shared ecosystem identity boundary with domain-specific authorization.

## Search/caching

SQL + Postgres FTS first; pgvector only for concrete semantic retrieval; no Redis initially.

## Future web deployment

A post-Phase-9 Next.js client may be deployed separately while continuing to use the same Health API, auth identity, and generated contracts. Its hosting choice should be made when the web phase begins rather than prematurely constraining the mobile roadmap.
