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
device. Import identity rows reference the canonical owner-scoped health
object and are removed by the future owner-erasure workflow.
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
