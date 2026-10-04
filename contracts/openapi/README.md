# OpenAPI contracts

`openapi.json` is a generated Phase 1 artifact from FastAPI. Do not edit it by hand. With the repository Python 3.12 environment active, run `pnpm --filter @personal-health/api-client generate`; this exports the contract without connecting to PostgreSQL and refreshes the generated TypeScript client. CI regenerates both artifacts and fails if Git detects drift.

The checked-in generator uses only Node's standard library because the npm registry could not be reached and no OpenAPI generator was available in the installed package store during Phase 1. It supports the schema forms emitted by the current service; its tests and implementation must be extended when adding new OpenAPI constructs. See [the API contract](../../docs/api/api-contract.md) for semantics and command details.
