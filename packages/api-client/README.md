# Generated API client

`src/generated.ts` is generated from `contracts/openapi/openapi.json`; `src/index.ts` is its stable package entry point. Import `ProfileApiClient`, `ApiError`, or the `components`/`operations` types from `@personal-health/api-client`. Both the mobile app and future web clients should use this package instead of duplicating request or response DTOs.

After activating the Python 3.12 virtual environment and installing the API development requirements, run:

```bash
pnpm --filter @personal-health/api-client generate
pnpm --filter @personal-health/api-client typecheck
pnpm --filter @personal-health/mobile test
```

Generation exports FastAPI's contract and runs the repository-owned Node standard-library generator; it performs no database or cloud request. The generator covers the OpenAPI schema subset currently used by the API. Unsupported additions must extend the generator before they are used. CI checks that a fresh generation leaves no tracked changes.
