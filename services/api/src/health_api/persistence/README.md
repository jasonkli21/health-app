# Persistence layer

`models.py` defines the canonical health tables plus the later daily and
planning tables. Phase 6 adds separate `action_proposals`, immutable
`action_proposal_revisions`, append-only `action_proposal_events`, and
`action_command_receipts`; pending proposals are not `health_objects`.
Phase 7 stores derived signals, insights, recommendations, and experiments as
typed `health_objects` with `analytics_artifacts` payload/lifecycle rows.
`analytics_evidence` references exact owner object revisions with restrictive
foreign keys, so historical evidence remains resolvable and input edits can
stale current derived artifacts without rewriting their original snapshots.
Phase 8 adds `healthkit_import_batches`, `healthkit_import_identities`, and
`healthkit_source_preferences`. They retain receipt/identity/preference
metadata only; native query anchors and raw HealthKit samples stay on the
device. Follow-up migration `20261007a0b1` allows tombstone identities without
a fabricated health object, tracks a bounded aggregate source revision and
user-archive state, and enforces date-only bounded step rows for new writes.
Object-linked import identities and tombstone-only identities are removed by
the future owner-erasure workflow. See the migration README for downgrade
limits.
JSON health payloads use PostgreSQL JSONB and are validated through typed
domain schemas before writes. Composite foreign keys include `owner_id` for
source, subtype, revision, proposal, receipt, and relationship references;
application queries also require the resolved principal.

`database.py` creates request-scoped synchronous SQLAlchemy sessions. Schema
changes are performed only by root Alembic migrations. Proposal receipts are
unique by owner/idempotency key and by owner/proposal/revision. SQL echo is off
so bound health values do not reach routine logs. Keep additional query/use-case
rules in the application layer and add new subtype tables only in their owning
phase.

The engine caps pool checkout and PostgreSQL connection establishment at one
second. Pooled connections carry a one-second statement timeout while idle so
SQLAlchemy's pre-ping is bounded; checkout clears that idle-only setting before
application work inside the current transaction, and rollback restores it.
`/readyz` separately uses a one-second transaction-local timeout for its
read-only `SELECT 1` probe.

Phase 9 adds `owner_deletion_jobs` and `owner_erasure_ledger`. The former keeps
only the authenticated request ID, lifecycle status, timestamps, and
sanitized failure code. The latter retains the owner UUID and erasure time as
input for a future isolated restore-replay step while backup retention is
unverified. The marker alone does not suppress an older database restore; no
restore replay runner is implemented.
Migration `20261007b1c2` adds database write guards to every current
owner-scoped table: inserts and updates take a shared owner-row lock and reject
owners whose lifecycle is no longer active. Deletes remain available to the
erasure transaction. Keep both the ORM inventory and migration trigger list in
sync when a future phase adds an owner table.
