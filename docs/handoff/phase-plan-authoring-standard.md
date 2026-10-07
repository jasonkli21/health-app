# Phase-plan maintenance standard

## Purpose

Use this standard when creating or materially revising an implementation plan.
The existing phase plans live under docs/implementation/phases/. Keep plans
repository-grounded and useful for future implementation, while making clear
that plans describe intended scope rather than delivery status. Current status
and open acceptance gates belong in docs/current-state.md and dated release or
review evidence. A plan alone does not authorize implementation.

## Output

Update only the plans needed for the authorized planning task. Preserve the
roadmap's accepted phase ordering and scope unless an explicit decision record
is changed. Add or revise the phase index when navigation or dependencies
change. Do not create release evidence as part of planning; the implementation
session records actual results in docs/implementation/evidence/.

## Planning principles

### Repository-grounded, not generic

Inspect the corrected Phase 0 repository before writing the plans. Name the actual packages, directories, service boundaries, contracts, commands, and conventions that exist. For paths/artifacts that cannot exist until an earlier phase is implemented, label them as **planned/provisional** rather than pretending they already exist.

### Self-contained for implementation

An implementing agent should be able to open a phase plan, inspect the current repo, reconcile any drift, and implement the phase without having to redesign the phase from scratch. Preserve the why behind important constraints, not only a checklist of files to edit.

### Reconciliation gate for every phase

Every plan begins with a short implementation-time reconciliation gate:

- inspect the current repository and preceding phase release evidence;
- confirm dependencies and accepted ADRs/contracts;
- identify drift between planned and actual paths/contracts;
- update the plan/ADR before code if a material design change is required;
- do not force implementation to match stale prose.

This is especially important for later phases because their exact file paths and APIs depend on code created by earlier phases.

### Strict phase boundaries

State what the phase delivers and explicitly defers. Do not pull later AI, cloud, HealthKit, record ingestion, or web work forward merely because it would be convenient. Preserve local/manual/disabled behavior when an integration is optional or unavailable.

### Concrete but not prescriptive for its own sake

Specify contracts, invariants, data ownership, error/failure behavior, migrations, tests, UI states, and important module boundaries. Do not prescribe low-value line-by-line implementation details, arbitrary class counts, or abstractions that have no demonstrated need.

### Verification is part of the implementation

Tests and verification are planned alongside functionality, not appended as a generic final step. Cover success, boundary, malformed input, authorization/ownership, temporal/provenance, idempotency/concurrency where relevant, unavailable integration, and rollback/migration behavior appropriate to the phase.

### Security, privacy, and provenance are cross-cutting

Preserve health-data privacy, owner scoping, minimal logging, explicit provenance, unknown-vs-zero semantics, temporal validity, and the distinction between user-confirmed/imported/derived information throughout the plans.

## Required structure for each phase plan

Adapt the structure to the phase rather than filling headings mechanically, but every plan should cover the following substance.

### 1. Phase header and baseline

Include:

- phase name and roadmap link;
- implementation status (`planned` initially);
- dependencies/prerequisites;
- assumed baseline from completed prior phases;
- implementation-time reconciliation gate.

### 2. Goal and user-visible outcome

State what becomes meaningfully possible after the phase and what architectural capability is established.

### 3. Scope boundary

Use explicit **Deliver** and **Defer / Out of scope** sections. Preserve the roadmap's intended phase boundary.

### 4. Decisions, assumptions, and invariants

Record decisions that are already accepted and identify genuine decisions that must be resolved before implementation. Do not reopen settled ADRs casually. Include important domain invariants and failure behavior.

### 5. Required implementation artifacts

As applicable, enumerate the concrete artifacts the phase must leave behind, for example:

- persisted records/tables/indexes/migrations;
- Pydantic/domain schemas;
- service/repository interfaces;
- REST/OpenAPI routes and generated-client impacts;
- configuration/environment flags;
- mobile screens/components/state/query boundaries;
- adapters/integration contracts;
- fixtures/evaluation datasets;
- docs/ADRs/release evidence.

Tables are useful when they make contracts clearer, but are not mandatory.

### 6. Data/API/UI/integration behavior

Describe the contracts in enough detail to eliminate major design ambiguity. Include ownership, validation, lifecycle, temporal behavior, provenance, pagination/bounds, idempotency, errors, loading/empty/error states, and offline/disabled behavior where applicable.

Do not invent a route/table simply to make the plan look complete; derive it from the architecture and phase needs.

### 7. Cross-cutting requirements

Capture requirements that apply across work packages, such as:

- health-data privacy and logging;
- authorization/owner scoping;
- unknown vs zero/false;
- provenance/confirmation state;
- temporal history;
- transaction boundaries;
- bounded external calls;
- deterministic behavior where the LLM must not be authoritative;
- local/cloud parity;
- accessibility and recoverable UX states.

### 8. Dependency map / execution order

Show the implementation dependency graph when the phase has multiple workstreams. The graph can be text/ASCII; it should explain which packages can proceed in parallel and which are gates.

### 9. Work packages

Break the phase into a small number of coherent, implementation-sized vertical or architectural slices. Name them `P<phase>.<n>` (sub-numbering is allowed when genuinely useful).

For every work package include:

- **Dependencies**
- **Goal**
- **Repository areas / planned artifacts** — actual paths when they exist; clearly marked provisional paths otherwise
- **Work** — concrete implementation changes
- **Requirements / invariants**
- **Tests / verification for this package**
- **Acceptance criteria**
- **Out of scope**

Prefer packages that can be reviewed and verified coherently. Do not create one package per tiny checklist item.

### 10. Migration, compatibility, and failure/rollback considerations

Where relevant, cover:

- forward/reversible DB migrations;
- compatibility with data from prior phases;
- generated-client/OpenAPI changes;
- local and cloud behavior;
- feature flags / disabled modes;
- retry/idempotency semantics;
- safe partial failure and rollback.

### 11. Verification matrix

Provide a phase-specific matrix or equivalent structured section mapping major risk areas to tests/fixtures/checks. Distinguish deterministic offline CI from checks that require real credentials, Apple capabilities, cloud deployment, or external provider verification.

Never claim mocks prove real provider/cloud/device behavior.

### 12. Phase acceptance criteria

Define end-to-end criteria for calling the phase complete. Include both product behavior and architectural/data-safety guarantees.

### 13. Completion review

End with a short set of questions that should all be answerable positively before advancing to the next phase.

### 14. Implementation handoff / release evidence

Specify what the implementation session should leave for the next phase: important routes/contracts, migration state, generated-client procedure, config/feature flags, verification commands/results, known external checks still unverified, and any release-evidence document to create.

## Phase-specific emphasis

Use the roadmap and architecture to vary depth appropriately:

- **Phase 1:** canonical model, schema/versioning, provenance, temporal/history invariants, migrations, Profile vertical slice.
- **Phase 2:** Event/Observation semantics, universal Add, Today read model/rollups, initial domain payload schemas, sparse/unknown behavior.
- **Phase 3:** local/cloud equivalence, auth and owner scoping, Neon/Cloud Run/GCS wiring, secrets, deployment checks, rollback and cost/safety bounds. Treat current vendor limits/terms as implementation-time verification gates rather than timeless facts.
- **Phase 4:** Goals/Regimens/Plans/Contexts/custom trackers, schedules, recurrence semantics, Today integration.
- **Phase 5:** read-only Health Context Builder and Personal AI boundary, context minimization/ranking, risk classification, disabled-service behavior, no canonical AI writes.
- **Phase 6:** typed action proposals, validation, confirmation, idempotency, audit/history, explicit direct-save exception.
- **Phase 7:** deterministic derived signals first, evidence-linked insights/recommendations, correlation-vs-causation boundaries, expiration, experiments and evaluation fixtures.
- **Phase 8:** native HealthKit boundary, fine-grained permissions, selective retention, sync cursors, dedupe, source precedence, device/local testing and explicit real-device verification gates.
- **Phase 9:** document/object-storage workflows, extraction-as-proposal, records/labs, export/deletion/backups, security/integrity/performance audit and end-to-end hardening.

## Final cross-plan review

After writing all nine plans, review them together and correct cross-phase inconsistencies. Specifically verify:

- each later phase depends only on capabilities earlier phases actually establish;
- one concept has one canonical owner;
- naming and API/data terminology remain consistent;
- no capability is accidentally implemented twice in different phases;
- deferred web work remains deferred;
- Personal AI/Health ownership stays intact;
- AI write restrictions remain intact;
- HealthKit does not become a wholesale cloud mirror;
- tests/source separation and generated-contract boundaries remain consistent;
- the plans do not silently introduce speculative infrastructure.

Planning edits do not authorize phase implementation. Follow the current user request and docs/current-state.md for the active scope.
