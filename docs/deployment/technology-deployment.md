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

## Health checks, request logs, and CI

`/healthz` is a dependency-free process liveness endpoint. `/readyz` runs a
read-only `SELECT 1` through the configured SQLAlchemy engine and returns only
a generic ready/unavailable status. The Cloud Run service uses `/readyz` for
startup and readiness probes and `/healthz` for liveness. Startup/readiness
checks gate traffic, while liveness checks restart unhealthy instances. They
do not verify Firebase, GCS, Neon parity, or optional Personal AI behavior.
Cloud Run readiness probes are
currently preview and require the service's Terraform `BETA` launch stage;
live behavior remains unverified.

Application request events are one-line JSON records with severity, validated
or generated request ID, method, route template, status code, and duration.
Body-size rejection adds a fixed reason and the configured limit. Application
logs omit query strings, headers other than the bounded request ID,
request/response bodies, health values, AI context, and raw exception details.
Cloud Run platform request logs have their own retention and access controls
and need live review.

CI runs Terraform formatting and validation with backend initialization
disabled, then builds the production API Dockerfile without pushing. It uses
the checked-in provider lock and requires no GCP credentials. These checks
validate source/configuration and image buildability; they do not apply
infrastructure or establish live cloud, database, or device behavior.

## Search/caching

SQL + Postgres FTS first; pgvector only for concrete semantic retrieval; no Redis initially.

## Future web deployment

A post-Phase-9 Next.js client may be deployed separately while continuing to use the same Health API, auth identity, and generated contracts. Its hosting choice should be made when the web phase begins rather than prematurely constraining the mobile roadmap.
