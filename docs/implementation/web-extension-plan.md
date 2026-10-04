# Post-mobile web application implementation plan

## Prerequisite

This plan begins **after the primary Phase 0–9 implementation is complete** and assumes the Health API is stable/deployed, mobile is substantially complete, auth is production-capable, the health model is mature, Personal AI works, insights/recommendations and records exist, native behavior is isolated, and OpenAPI client generation is reliable.

This is a separate roadmap. It does not alter the mobile-first Phase 0–9 plan.

## Web Phase W0 — Readiness audit and shared-boundary extraction

Audit the final API for client assumptions; move genuinely reusable frontend logic into shared packages; confirm native imports are mobile-only; stabilize generated API client/versioning; formalize design tokens; document deliberate platform differences.

Exit: no direct web DB access, native deps do not leak, shared packages stay small, backend gaps are known before UI work.

## Web Phase W1 — Next.js foundation

Create `apps/web` with Next.js/React/TypeScript, lint/typecheck/tests, auth/session integration, generated API client, shared domain/design tokens, app shell/navigation, loading/error/empty conventions, local/cloud configuration. Placeholder pages only.

## Web Phase W2 — Profile and Today read experiences

Implement Profile overview/categories/details, Today dashboard, timeline/events/observations, active contexts, regimen/plan status, source/provenance display. Use large-screen layouts rather than literal mobile copies.

## Web Phase W3 — Structured editing and universal Add

Implement profile editing, event/observation entry, universal Add, goals/regimens/plans, custom tracker management, useful bulk/multi-field editing, and AI proposal review. Preserve the same write/confirmation semantics as mobile.

## Web Phase W4 — Insights and longitudinal analytics

Build trend dashboards, period comparisons, insight evidence, recommendation history, experiment results, configurable chart ranges, drill-down to source observations/events, export-friendly views. Use the same backend-derived truth.

## Web Phase W5 — Records and document review

Implement record library/viewer, side-by-side document + structured extraction review, approve/reject/correct flows, and longitudinal lab comparison where backend support exists. Keep object access private/signed.

## Web Phase W6 — Assistant and research workspace

Build long-form health conversations, visible context scope, cited research where Personal AI supports it, relevant-context side panels, recommendation/proposal review, and explicitly authorized cross-domain workflows. Do not add a second model-provider stack.

## Web Phase W7 — Desktop planning workspace

Add calendar/week views, drag/reorder/reschedule where domain semantics allow, goal-plan links, experiment authoring, custom tracker builder/editor, and program templates if backend-supported. Use the same domain commands as mobile.

## Web Phase W8 — Accessibility, responsive behavior, and hardening

Keyboard navigation, screen-reader/semantic audit, responsive behavior, performance/bundle audit, cross-browser tests, security review, auth expiration cases, record access tests, error/retry behavior, E2E regression coverage.

## Web Phase W9 — Parity review and platform specialization

Identify intentional mobile-only/web-only capabilities, close accidental gaps, remove duplicate utilities/components, verify shared packages did not become dumping grounds, and update architecture/ADRs for the final multi-client system.

## Explicitly deferred

No browser HealthKit replacement, no exact visual parity, no replacement of FastAPI by Next.js APIs, no second AI orchestration stack, and no direct Neon/GCS browser access except intentionally signed object flows.

## Target architecture

```text
                       Personal AI
                            │
                            ▼
                       Health API
                    ┌───────┼────────┐
                    ▼       ▼        ▼
                 Postgres   GCS    Analytics/
                                  derived state
                    ▲
              ┌─────┴─────┐
              │           │
              ▼           ▼
          Mobile App    Web App
          Expo / RN     Next.js
              │
           HealthKit
```
