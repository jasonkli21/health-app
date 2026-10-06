# Phase 6 local implementation evidence

**Checkpoint:** October 5, 2026. The typed proposal store, owner API,
transactional executor, generated client, and mobile review flow are locally
implemented. This does not establish live Personal AI proposal submission or
database/device release acceptance.

## Reconciliation and scope

Phase 5 evidence confirms that there is no supplied Personal AI endpoint,
service identity, user-delegation capability, tool callback, or retention
contract. Its adapter is disabled, and `PERSONAL_AI_ENABLED=true` is rejected
by settings validation. No provider route, capability, URL, credential, or
authorization behavior was invented.

The owner-authenticated `POST /action-proposals` route creates an
owner-authored pending draft. AI service submission is unavailable until the
actual provider contract is supplied and reviewed. Apply and reject use the
normal verified user-owner dependency; the API does not accept service tokens
as confirmation. The change records that reconciliation in ADR 0006 and the
Phase 6 implementation plan before code.

## Implemented commands and persistence

The strict, versioned command union under `health_api.domain.proposals` allows:

- `profile.create`, `profile.update`
- `event.create` with zero or more explicitly linked supported Observations
- `goal.create`, `goal.update`
- `plan.create`, `plan.update`
- `tracker.create`

Unknown fields are forbidden. No archive/delete, permission change, privilege
grant, arbitrary path, or generic JSON patch command is accepted. A proposal
contains 1–10 commands, up to 20 evidence refs, bounded rationale, at most
65,536 bytes of canonical content, and server-configured expiry (default 24
hours, maximum 7 days). Create target IDs are generated deterministically from
the proposal ID, command position, and action. IDs remain stable across retries
and edits that keep a create command in the same position with the same action;
each saved revision keeps its generated IDs.

Additive migration `e7f6a5b4c3d2` (head) adds:

- `action_proposals`: owner, origin, current revision/hash, expiry, state,
  confirmer/rejection fields, validation summary, and committed result.
- `action_proposal_revisions`: immutable versioned typed command/evidence
  snapshots.
- `action_proposal_events`: append-only lifecycle audit events.
- `action_command_receipts`: idempotency key, proposal revision, content hash,
  and committed result.
- nullable `health_object_revisions.proposal_id` provenance link.

Proposal records are separate from canonical `health_objects`. Target resource
history keeps the authenticated owner as actor, records `proposal_id`, and
preserves `user_confirmed` status. A future AI-originated proposal will use an
AI source row; this local owner-authored endpoint labels its source manual as
`Confirmed proposal`.

## API and apply behavior

The generated API includes `POST/GET /action-proposals`, detail and history,
`PATCH /action-proposals/{id}`, and `/apply` and `/reject` actions. Lists are
owner-scoped, keyset paginated (default 50, maximum 100), and the cursor binds
to owner and state filter. The server assigns the proposal origin; callers
cannot set owner, actor, source, or origin metadata.

Apply requires the exact displayed `proposal_revision` and `content_hash`, an
idempotency key of at most 128 characters, and
`confirmation: "explicit_user_save"`. It locks the proposal, verifies expiry,
current evidence and target revisions, and runs existing Profile, daily, and
planning application commands in one outer transaction. Nested savepoints
allow those commands to compose without committing independently. Proposal
state, target writes, source/provenance, target histories, lifecycle event,
and receipt commit together. An execution failure rolls the batch back and
leaves the proposal pending with a sanitized validation summary. There is no
persisted `applying` state.

Receipts are unique on `(owner_id, idempotency_key)` and
`(owner_id, proposal_id, proposal_revision)`. A same-proposal, same-key,
same-content retry returns the recorded result; key reuse with a different
proposal/content returns 409. A proposal applied concurrently under different
keys returns the single original result. Stale target/evidence content requires
refresh and a new proposal revision/confirmation; the server never rebases.

A Plan can reference an earlier `goal.create` command in the same proposal.
The target Goal ID is shown in the result and remains stable when that create
command retains its position and action in a later draft revision. Forward
references are rejected.

## Mobile confirmation contract

The Assistant inbox requests a pending-only, paginated summary by default and
offers separate filters for applied, rejected, expired, and superseded history.
The list DTO omits command/evidence payloads; opening an item fetches its full
immutable review detail. Details include the source, expiry, rationale, target
and expected revision, typed values including time/unit fields, evidence
title/type/revision, and revision-bound before/after updates. Profile review
identifies preserved and cleared optional fields. Plan review identifies
removed items and active schedules that will be retired. “Confirm and save”
applies the displayed revision directly; there is no second dialog. Its
idempotency key is deterministic from proposal ID and revision. After an
uncertain network result the screen fetches the proposal and uses that same
key for replay. A known stale-reference conflict shows owner-scoped current
record snapshots and revisions; the owner can edit evidence references or
target baselines and save a new immutable proposal revision/hash. An open edit
retains its original revision baseline across refresh and focus changes, so
concurrent edits conflict without discarding the local draft. The JSON editor
is a local compromise and may later be replaced with command-family forms.
Reject and applied/expired states are distinct. Session remount clears this
in-memory state.

The explicit direct-save exception is not connected to AI-prefilled Profile,
daily, or planning forms because the provider is unavailable. Existing manual
structured forms retain their existing save behavior.

## Configuration and generation

- `ACTION_PROPOSAL_TTL_HOURS=24` is a server-only setting bounded to 1–168.
- `ACTION_PROPOSAL_GENERATION_ENABLED=true` is an independent server-side
  kill switch for new owner-authored proposal creation. Setting it false denies
  POST creation while detail/list reads and rejection of existing proposals
  remain available. AI-originated proposals remain rejected until the
  current-context safety policy and external provider contract are configured.
- `PERSONAL_AI_ENABLED=false` remains the Phase 5 default and cannot be set to
  true until the external contract is configured.
- OpenAPI and the generated TypeScript client were regenerated together with
  the repository-owned exporter and generator:

  ```bash
  PYTHONPATH=services/api/src .venv/bin/python services/api/scripts/export_openapi.py
  /Users/jasonkli/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node packages/api-client/scripts/generate-client.mjs
  ```

## Local verification after independent review

- API: `.venv/bin/pytest -c services/api/pyproject.toml services/api/tests -q`
  — **135 passed, 50 skipped**. The added PostgreSQL atomic rollback and
  cross-owner detail tests are among the skips because `TEST_DATABASE_URL` is
  not configured; existing DB-gated checks remain skipped as well.
- Mobile: bundled Node running `apps/mobile/node_modules/vitest/vitest.mjs run
--root apps/mobile` — **98 passed across 21 files**. Mobile TypeScript passes.
- Full configured Ruff format check passes. The six proposal-review import
  blocks and the settings import block pass the exact configured Ruff check.
  Full configured Ruff check still reports **17 inherited I001 import-order
  failures outside the changed review files**.
- Configured mypy reports **6 inherited errors in unchanged
  `application/ai_context_service.py`**; the proposal service has no mypy
  errors.
- OpenAPI export, TypeScript client generation, Prettier checks, and
  `git diff --check` pass. `alembic heads` reports one merged head,
  `20261006b1a2`.
- PostgreSQL was not available. The migration was not applied; ORM drift,
  database atomic rollback, real concurrent apply/daily lock races, and
  receipt races remain unverified. Two newly added DB integration tests were
  collected and skipped without `TEST_DATABASE_URL`.
- Offline `alembic upgrade head --sql` generates the merged migration graph.
  The receipt-key migration's downgrade refuses once more than one accepted
  key exists for a proposal revision.

## Open gates before Phase 6 release acceptance

- Extend deterministic API/domain checks for every allowed and forbidden
  command family, owner isolation across all routes, evidence staleness, expiry,
  and proposal revision changes. Local review regression tests now cover
  serialization presence, stale-reference hints, archived Profile targets,
  reference-revision hashing, receipt revision/key binding, and bounded list
  summaries.
- Apply the migration to disposable PostgreSQL; verify upgrade/downgrade
  refusal behavior and ORM drift.
- Exercise same-key and different-key concurrent applies, same-proposal
  concurrent applies, injected failures between commands, receipt replay, and
  apply/reject races against PostgreSQL.
- Run the mobile suite and a device walkthrough for exact diff readability,
  time/unit presentation, accessibility, double-tap behavior, lost responses,
  draft recovery, and account switching.
- Supply and review the real Personal AI service identity, delegated owner
  capability, proposal registration/callback, retry/timeout, and retention
  contracts; then perform the real role and owner-isolation checks. The fake or
  disabled adapter cannot establish this behavior.
- Review the current JSON command editor with users and replace it with
  accessible command-family forms before broad product rollout if it proves
  difficult to review safely.
