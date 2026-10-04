# Phased implementation plan

The scaffold is currently **Phase 0 only**. Each phase should begin with a repository-wide reconciliation against this plan. If the code reveals a better design, update the plan/ADR first rather than forcing implementation to match stale prose.

Detailed documentation-only execution plans: [phase index](phases/README.md). Reconcile each plan immediately before implementation.

## Phase 0 — Repository foundation

Goal: a clean, verifiable handoff surface without substantive health features.

Scope:

- monorepo layout;
- Expo mobile shell;
- FastAPI shell;
- local PostgreSQL dependency;
- migration/tooling placeholders;
- source/test separation;
- OpenAPI client-generation boundary;
- CI/lint/typecheck/test hooks;
- core product/UX/architecture/data/security/AI docs;
- environment examples and local setup;
- scaffold verification script.

Exit criteria:

- repository structure is coherent and documented;
- API healthcheck can run;
- mobile shell can run after dependency install;
- local Postgres can start;
- no Phase 1 tables/features are accidentally implemented;
- Codex can state the next implementation step without needing hidden context.

## Phase 1 — Canonical health model and Profile

Implement:

- users/principals;
- health object identity/common metadata;
- sources/provenance;
- profile items;
- temporal validity/history;
- relationships;
- schema registry/versioned Pydantic payloads;
- profile CRUD/query services and initial Profile UI;
- migrations and tests.

Do not add AI yet.

## Phase 2 — Daily health data

Implement:

- Events;
- Observations;
- Today query;
- daily rollups;
- universal Add;
- manual logging;
- profile ↔ Today UX.

Initial domains:

```text
nutrition
exercise
sleep
symptoms
measurements
```

## Phase 3 — Cloud baseline

Wire:

```text
Neon
Cloud Run
Firebase Auth
GCS
```

while keeping local equivalents working.

Deploy early enough that cloud incompatibilities don't accumulate.

At this point you have:

```text
local mode
+
cloud mode
```

similar to the other applications.

## Phase 4 — Personal planning

Add:

- goals;
- regimens;
- plans;
- active contexts;
- custom trackers;
- schedules;
- Today plan items.

At this point the non-AI product should already be useful.

## Phase 5 — Personal AI integration

Implement:

```text
Health Context Builder
Health search
Personal AI tools
Assistant UI
```

Start **read-only**.

Questions work, but the AI cannot change health state.

## Phase 6 — AI action proposals

Add:

- profile mutation proposals;
- event proposals;
- goal proposals;
- plan proposals;
- tracker creation proposals;
- confirmation UI.

Now:

> “I started taking creatine.”

can become structured state safely.

## Phase 7 — Insights and recommendations

Add:

- derived signals;
- trend computation;
- basic association analysis;
- insights;
- recommendation objects;
- evidence/provenance;
- recommendation expiration;
- experiments.

This is where the health application starts becoming substantially more than a tracker.

## Phase 8 — HealthKit

Add selective integrations:

**First wave**

```text
workouts
sleep
steps
weight
resting HR
heart rate summaries
```

Then implement:

```text
import policy
deduplication
sync cursors
source precedence
aggregation
```

Don't do every HealthKit type.

## Phase 9 — Records and hardening

Add:

- document uploads;
- lab extraction;
- user review;
- structured imported observations;
- export;
- backups;
- deletion workflow;
- security audit;
- integration tests;
- performance testing;
- data integrity audit.

Only after this would I seriously expand into things such as:

- Garmin;
- Strava;
- Oura;
- provider records/FHIR;
- sophisticated nutrition databases;
- advanced N-of-1 statistics.
