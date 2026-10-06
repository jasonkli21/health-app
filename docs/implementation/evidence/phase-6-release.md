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

The Assistant includes an in-memory proposal inbox. Each card shows the source,
expiry, rationale, target and expected revision, typed values including
time/unit fields, and evidence title/type/revision. “Confirm and save” applies
the card's displayed revision directly; there is no second dialog. Its
idempotency key is deterministic from proposal ID and revision. After an
uncertain network result the screen fetches the proposal and uses that same
key for replay. Editing typed command JSON creates a new immutable proposal
revision/hash and requires a fresh confirmation; the current editor is
functional but less approachable than command-family-specific forms. Reject
and applied/expired states are distinct. Session remount clears this in-memory
state.

The explicit direct-save exception is not connected to AI-prefilled Profile,
daily, or planning forms because the provider is unavailable. Existing manual
structured forms retain their existing save behavior.

## Configuration and generation

- `ACTION_PROPOSAL_TTL_HOURS=24` is a server-only setting bounded to 1–168.
- `PERSONAL_AI_ENABLED=false` remains the Phase 5 default and cannot be set to
  true until the external contract is configured.
- OpenAPI and the generated TypeScript client were regenerated together with
  the repository-owned exporter and generator:

  ```bash
  PYTHONPATH=services/api/src .venv/bin/python services/api/scripts/export_openapi.py
  /Users/jasonkli/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node packages/api-client/scripts/generate-client.mjs
  ```

## Local static checks

- Changed API/domain/persistence/migration Ruff check — passed.
- `mypy services/api/src/health_api` — passed, 35 source files.
- Mobile `tsc --noEmit -p apps/mobile/tsconfig.json` — passed.
- ESLint on the changed Assistant feature files — passed.
- Prettier on changed mobile, OpenAPI, and generated client artifacts — passed.
- FastAPI OpenAPI export and TypeScript client generation — passed.
- `alembic heads` reports a single head, `e7f6a5b4c3d2`.
- Offline `alembic upgrade head --sql` generated the full migration chain.
- API and mobile test suites were not run in this implementation session.
- No PostgreSQL database was available to apply the migration, verify ORM
  drift, exercise transaction rollback/receipt races, or inspect locks.
- `git diff --check` is recorded after the final source/doc pass.

## Open gates before Phase 6 release acceptance

- Run deterministic API/domain checks for each allowed and forbidden command,
  owner isolation, evidence staleness, expiry, and proposal revision changes.
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
