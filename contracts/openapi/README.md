# OpenAPI contracts

`openapi.json` is a generated Phase 1 artifact from FastAPI. Do not edit it by hand. With the repository Python 3.12 environment and supported Node runtime active, run `pnpm --filter @personal-health/api-client generate`; this exports the contract without connecting to PostgreSQL and refreshes the generated TypeScript client. CI regenerates both artifacts and fails if Git detects drift.

The checked-in generator owns the emitted TypeScript transport methods and
uses the repository's pinned Prettier dependency to keep generated output
consistent with the workspace. It preserves object fields when an OpenAPI
schema combines them with `allOf` constraints. Extend its handling before
adding a new OpenAPI construct.
See [the API contract](../../docs/api/api-contract.md) for semantics and
command details.
