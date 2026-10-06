# Logical data model

The model supports structured common health concepts, custom user-defined information, temporal correctness, provenance, confirmation status, sparse tracking, and longitudinal analysis.

Core vocabulary: Fact/profile item, Constraint, Preference, Regimen, Goal, Plan, Active context, Event, Observation, Tracker definition, Experiment, Derived signal, Insight, Recommendation, Record, Relationship, Action proposal.

A common `health_objects` envelope should include identity, user, object type/domain/status, title, validity window, recorded/created/updated times, source, confirmation status, schema version, notes, and metadata JSONB.

Missing observation != zero != false.

Use relational columns for identity/lifecycle/time/source/common query keys and validated JSONB for type-specific extension payloads.

Subtype areas include `profile_items`, `observations`, `events`, `regimens`, `goals`, `plans`, `contexts`, `tracker_definitions`, `experiments`, `derived_signals`, `insights`, `recommendations`, `records`, `health_relationships`, and `action_proposals`.

Quantities store value plus unit. Provenance distinguishes manual, confirmed, device imported, document/provider imported, AI extracted/derived, and system computed. AI inference never silently becomes a confirmed fact.

Device retention preserves useful low-frequency samples while leaving high-frequency raw streams in HealthKit/external sources unless a feature requires them.

## Phase 4 planning, schedules, and custom trackers

Migration `d4e5f607a8b9` extends the existing owner-scoped `health_objects`
envelope for goals, regimens, plans, contexts, and tracker definitions. Each has
a typed `planning_resources` payload and subtype lifecycle; the shared envelope
still owns identity, manual provenance, permissions, revision, and history.
`planning_links` stores ordered stable plan items and explicit context
relevance. Owner-consistent foreign keys prevent cross-owner links. Plan-item
rows keep their IDs when the plan is edited or reordered so schedules remain
attached to the intended item.

Schedules represent intent. `planning_schedule_identities` assigns a stable ID
to a regimen or plan item, and immutable `planning_schedules` rows hold
effective-dated revisions. Occurrence keys encode the schedule ID and original
local date/time, so a future edit does not rewrite prior actions. Explicit
`planning_occurrence_overrides` store completed, skipped, or rescheduled state;
`planning_occurrence_actions` records each user action revision. Occurrences
are expanded for bounded reads instead of materialized indefinitely. Local
slots use the schedule's IANA timezone, resolving a spring gap to the next
valid minute and a fall overlap to its earlier offset. A rescheduled slot keeps
its original key and appears on the new due day.

Tracker definitions live as planning resources, while immutable
`tracker_schema_versions` rows retain each field schema. Custom entries remain
Observations: `observations.metric_key` is `custom`, its numeric summary value
is null, and it stores the owner tracker ID, schema version, and a flat map of
field IDs to validated values. Definition edits append a schema version;
older observations continue to reference their original version. Archiving a
tracker blocks new entries but does not remove its schema or observations.
Custom values do not enter the existing fixed-metric Today summaries.

Missing optional tracker fields are absent; explicit `false` and `0` remain
values. Custom fields are limited to 20 per definition, 50 choices per enum,
2,000 characters per text field, and 16 KiB per definition. Supported fields
are text, number, boolean, enum, date, and quantity with a declared unit. No
field executes code or derives clinical meaning.

## Phase 6 action proposal storage

Pending proposals are not `health_objects`: until confirmation they are
candidate commands rather than health facts. `action_proposals` owns the
proposal's lifecycle, origin kind, expiry, current revision/hash, and terminal
confirmation/result fields. `action_proposal_revisions` stores immutable
versioned typed command/evidence snapshots. `action_proposal_events` records
created, edited, applied, rejected, and expiry transitions. All are
owner-scoped with owner-consistent foreign keys.

`action_command_receipts` records each accepted idempotency key, canonical
content hash, and committed result. It is unique by `(owner_id,
idempotency_key)`; multiple keys may point to one committed proposal revision.
Target object revisions carry an
optional `proposal_id`, so provenance can be inspected without rewriting the
canonical target history actor: the verified owner remains the actor, source
origin is retained, and confirmation status is `user_confirmed`.

The Phase 6 command union is closed over Profile create/update, Event create
with linked supported Observations, goal create/update, plan create/update,
and tracker-definition create. It reuses the existing payload registries,
revision validation, and owner-reference checks. There are no archive/delete,
permission-grant, or arbitrary patch commands. The provider adapter remains
disabled until its actual identity/delegation/tool contract is reviewed.

## Phase 1 Profile v1 contract

Phase 1 registers only `profile_item` schema version 1. Its payload has `kind`, `category`, stable lower-case `key`, display `label`, and a required `value`. A JSON `null` value means unknown. Tagged values are `text`, `boolean`, finite `number`, finite `quantity` with a supported unit, and a bounded `text_list`. `false` and `0` remain known values. Extra payload fields and unregistered type/version pairs are rejected. Category and kind must agree: fact/background, constraint/constraints, preference/preferences.

Profile validity instants must include an offset and are normalized to UTC. Windows are half-open `[valid_from, valid_to)`; either bound may be absent, and two supplied bounds must be ordered. Recorded/created/updated times describe when Health knew the item. They do not replace effective validity. Manual structured saves are `user_confirmed`; provenance remains a separate source field. `ai_use_allowed` and `cross_domain_use_allowed` both default to false. Phase 1 stores only bounded display metadata, not unvalidated health payloads.

The schema registry is additive: a later payload version gets a new `(object_type, schema_version)` entry and a migration/conversion policy that keeps old revision snapshots readable. Existing registered versions are immutable. Phase 1 does not register event, observation, regimen, or other later-phase schemas.

## Phase 1 relational representation

Alembic revision `22dad79c2ee1` creates only `users`, `sources`, `health_objects`, `profile_items`, `health_object_revisions`, and `health_relationships`. `health_objects` holds common identity, owner, type/domain/status, title, validity/recorded/created/updated instants, source, confirmation, schema version, revision, notes, bounded JSONB metadata, AI/cross-domain permission bits, and the immutable create fingerprint. `profile_items` holds the queryable kind/category/key plus the registry-validated versioned payload. Manual items refer to a per-owner `manual` source.

The subtype, source, revision, and relationship foreign keys include `owner_id`, so PostgreSQL rejects a child/source/edge that crosses users even if application code is bypassed. History snapshots include both the common envelope and Profile payload; create is revision 1, and every successful update/archive appends the next revision in the same transaction. A stale expected revision leaves both current state and history unchanged. The create fingerprint covers canonical initial content and permissions; a repeated same-owner ID with the same content returns the current object even after later edits, while a different create body returns conflict and cannot reset it. Archiving advances history and removes the item from the active temporal list while retaining owner-only detail/history.

Index paths cover owner/status/current-list ordering, owner/category/key, unique owner/object/revision history lookup, and both directions of owner-scoped relationships. No later-phase subtype tables are created.
