# Future web extension architecture

## Status

Deferred until the initial mobile/backend implementation is complete. This document exists now so the mobile-first implementation preserves a clean web extension path without adding web scope to Phases 0–9.

## Goal

Add a first-class desktop/web experience over the **same Health backend and canonical health model**. The web client is another presentation surface, not a second health system.

## Recommended future stack

- Next.js
- React
- TypeScript
- TanStack Query or equivalent server-state layer
- generated `@personal-health/api-client`
- shared `@personal-health/domain` frontend types/utilities
- shared `@personal-health/design-tokens`
- shared identity/authentication boundary used by mobile

## Future repository shape

```text
personal-health/
├── apps/
│   ├── mobile/          # Expo / React Native
│   └── web/             # Future Next.js client
├── services/
│   └── api/             # Shared Health API
├── packages/
│   ├── api-client/      # Generated API client
│   ├── domain/          # Frontend-safe shared health types/utilities
│   ├── design-tokens/   # Cross-platform visual tokens
│   └── shared/          # Small set of truly shared frontend helpers
└── contracts/
```

## Ownership boundaries

Backend/shared authority remains: canonical health state, data model, temporal/provenance semantics, authorization, context builder, Personal AI integration, derived signals/insights/recommendations, records/storage, API contracts.

Mobile-specific: HealthKit, notifications, camera capture, native background sync, touch-first logging.

Web-specific: desktop navigation, large tables/charts, document review, keyboard workflows, multi-column editing, large-screen Assistant/research.

## Shared code philosophy

Optimize for shared contracts and domain-facing logic, not maximum UI component reuse. Share the generated API client, DTO-facing types, quantity/date formatting, grouping helpers, design tokens, and framework-compatible helpers. Do not force every React Native component to render on web.

## Native integration isolation

Native-only modules stay behind mobile adapters. Shared packages and web must never import iOS-native modules transitively.

```text
HealthDataSource
├── ApiHealthDataSource
└── HealthKitDataSource   # mobile only
```

## Authentication and API interaction

Web reuses the same identity and Health API. Both mobile and web consume the generated client from FastAPI/OpenAPI. Do not create direct browser database access or duplicate domain business logic in Next.js.

## Product split

Mobile specializes in quick daily capture, measurements, workouts, notifications, HealthKit, and Today. Web specializes in longitudinal analysis, detailed Insights, profile/plan editing, records/labs, experiments, custom trackers, and long-form Assistant/research.

## Non-goals during mobile phases

No `apps/web` implementation yet; no web/mobile feature-parity requirement; no React Native Web requirement for every component; no premature shared-component abstraction.
