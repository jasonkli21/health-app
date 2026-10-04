# Personal Health

A mobile-first personal health application that maintains a structured, extensible health model and integrates with the Personal AI System for context-aware reasoning, research, insights, and recommendations.

This repository is intentionally scaffolded for Codex handoff. It includes product, UX, architecture, data-model, security, AI-boundary, deployment, and phased implementation documentation plus minimal runnable shells. Substantive product phases are not implemented yet.

## Product thesis

The app is a personal health operating system rather than a single-purpose tracker. It combines durable profile facts and constraints, goals/regimens/plans/temporary contexts, daily events and observations, extensible custom trackers, longitudinal signals and insights, and user-approved AI recommendations/mutation proposals.

The Health app owns canonical health state. The Personal AI System owns model orchestration, general conversation, research, and cross-domain reasoning.

## Intended stack

- Mobile: React Native + Expo + TypeScript + Expo Router
- API: Python + FastAPI + Pydantic
- Persistence: PostgreSQL locally; Neon Postgres in cloud
- ORM/migrations: SQLAlchemy 2 + Alembic
- Cloud compute: Google Cloud Run
- Object storage: local filesystem in development; Google Cloud Storage in cloud
- Identity: shared identity boundary, initially compatible with Firebase Auth
- AI: Personal AI System through typed health-domain APIs/tools
- Health integrations: HealthKit later through a native adapter; selective sync only
- Future web: Next.js + React + TypeScript over the same Health API, after the mobile/backend roadmap is complete

## Repository layout

```text
apps/mobile/              Expo shell; product UI lives here
services/api/             FastAPI health-domain service
packages/api-client/      Generated/wrapped TypeScript API client
packages/domain/          Frontend-safe shared health types/utilities
packages/design-tokens/   Cross-platform visual tokens
packages/shared/          Small set of truly shared frontend helpers
contracts/                OpenAPI and shared schema artifacts
migrations/               Database migrations
infra/                     Local Docker and GCP deployment assets
scripts/                   Developer automation
docs/                      Product, UX, architecture, AI, security, plans
```

A future `apps/web/` client is explicitly planned but is **not** part of the initial Phase 0–9 roadmap. See `docs/web/web-extension-architecture.md` and `docs/implementation/web-extension-plan.md`.

## Local bootstrap

Use the complete [local development guide](docs/local-development.md) for setup, environment boundaries, and verification. Prerequisites: Python 3.12 (tested), Node >=22.13, pnpm 9.15.0, Docker Compose, and compatible Xcode/Expo Go for iOS execution.

```bash
cp .env.example .env
docker compose up -d postgres
pnpm install --frozen-lockfile
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -c services/api/requirements-dev.lock -e 'services/api[dev]'
uvicorn health_api.main:app --reload --app-dir services/api/src --host 127.0.0.1
```

In another terminal, run `pnpm mobile:start`. The mobile shell uses Expo Go; Phase 0 has no API calls and the API healthcheck does not yet consume the environment settings or connect to Postgres.

## Current implementation boundary

Only Phase 0 repository foundation is scaffolded. Do not infer that documented Phase 1+ behavior already exists. The web extension roadmap is deferred until after Phase 9.

Read these first:

1. `CODEX.md`
2. `docs/project-brief.md`
3. `docs/architecture/architecture.md`
4. `docs/data/data-model.md`
5. `docs/ai/personal-ai-integration.md`
6. `docs/implementation/implementation-plan.md`
7. `docs/handoff/phase-plan-authoring-standard.md`
8. `docs/handoff/codex-handoff.md`

Detailed Phase 1–9 execution plans are indexed in [docs/implementation/phases/README.md](docs/implementation/phases/README.md). The [Phase 0 review](docs/handoff/phase-0-review.md) records foundation fixes and validation limits.
