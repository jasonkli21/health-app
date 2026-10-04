# ADR 0007 — Future web application is a separate client over the same Health API

Status: Accepted

## Decision

The initial implementation remains mobile-first. After the Phase 0–9 mobile/backend roadmap, add a separate Next.js web client rather than requiring the mobile UI to run unchanged on web.

The future web app reuses the same Health API, authentication identity, generated API client, canonical state, AI integration, and selected frontend-safe packages. HealthKit/native integrations remain mobile-only.

## Why

This preserves maximum backend/domain reuse while allowing mobile and desktop to specialize for their strongest workflows. It avoids coupling mobile implementation to React Native Web constraints and avoids a second backend or duplicate health business logic.
