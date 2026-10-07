# Repository architecture

## Mobile

Use feature-oriented organization under `apps/mobile/src/features/`. Native integrations remain behind mobile-specific adapters.

## Future web

`apps/web` is not implemented. The intended web client is a separate Next.js app over the existing Health API; see the separate web plan. Current delivery status is in [current state](../current-state.md).

## Shared frontend packages

- `packages/api-client`: generated API client
- `packages/domain`: frontend-safe health types/utilities
- `packages/design-tokens`: cross-platform visual tokens
- `packages/shared`: small set of truly reusable helpers

Do not move backend business logic into frontend packages and do not force cross-platform component reuse.

## API

Source under `services/api/src/health_api`; tests under `services/api/tests`.

## Contracts

FastAPI/OpenAPI is the source for generated client contracts.

## Docs

ADRs record settled decisions; implementation plans must be updated only when a deliberate deviation is made.
