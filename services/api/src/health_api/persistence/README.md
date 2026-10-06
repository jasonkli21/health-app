# Persistence layer

`models.py` defines the canonical health tables plus the later daily and
planning tables. Phase 6 adds separate `action_proposals`, immutable
`action_proposal_revisions`, append-only `action_proposal_events`, and
`action_command_receipts`; pending proposals are not `health_objects`.
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
