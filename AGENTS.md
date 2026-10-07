# Repository operating guide

Start with [the documentation router](docs/README.md) and
[current state](docs/current-state.md). Read only the task-specific sources
they route to; phase plans are scope references, not evidence that work shipped
or authorization to begin it.

## Source of truth

When sources disagree, use this order:

1. Current code, executable schemas/contracts, migrations, and tests.
2. Release, review, and verification evidence.
3. Accepted ADRs and other decision records.
4. Product, architecture, data, security, and deployment intent.
5. Active implementation plans.
6. Historical or superseded documents, for context only.

Security and privacy constraints apply throughout. Reconcile any phase plan
with the repository and preceding evidence before substantive phase work.

## Engineering boundaries

- Keep production source and tests in separate directories.
- Keep FastAPI routes thin; put validation, ownership, transactions, and domain
  behavior in the application/domain layers.
- The Health service owns canonical health state and its history. Personal AI
  is an optional reasoning boundary, never the health database.
- Never give Personal AI database credentials. Send only explicitly consented,
  purpose-scoped, minimized Health context through a reviewed typed contract.
- AI-originated changes use closed, typed proposals and explicit confirmation.
  A deliberate save in an already structured user flow may commit directly.
- Preserve provenance, temporal validity, and unknown-versus-zero/false
  semantics. Use relational structure for queryable fields and validated,
  bounded JSONB for extensible payloads.
- Keep object storage private. Real sensitive ingress requires verified
  authentication and private cloud storage; ordinary development uses
  synthetic data and local services.
- Never put health payloads, credentials, bearer tokens, or sensitive request
  bodies in routine logs, fixtures, or review records.
- Keep local and cloud modes portable. Do not add speculative infrastructure
  such as a queue, external vector database, or cache without demonstrated need.
- Keep native integrations inside mobile-specific adapters. Shared packages
  used by a future web client must not import native modules transitively.
- Prefer code, contracts, tests, and linters over prose when they can enforce
  an invariant.

## Working and verification

Before changing a complex subsystem, read its local README and the relevant
route in docs/README.md. Before implementing planned work, compare the active
plan with code, accepted decisions, and the latest release evidence; update the
plan or ADR first if the design materially changed.

Run focused checks for changed code and documentation links. For API contract
changes, verify OpenAPI and generated-client consistency; for schema changes,
verify Alembic heads and migration/model agreement. Do not claim database,
provider, cloud, or device behavior from mocks or static checks.
