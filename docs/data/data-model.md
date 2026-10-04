# Logical data model

The model supports structured common health concepts, custom user-defined information, temporal correctness, provenance, confirmation status, sparse tracking, and longitudinal analysis.

Core vocabulary: Fact/profile item, Constraint, Preference, Regimen, Goal, Plan, Active context, Event, Observation, Tracker definition, Experiment, Derived signal, Insight, Recommendation, Record, Relationship, Action proposal.

A common `health_objects` envelope should include identity, user, object type/domain/status, title, validity window, recorded/created/updated times, source, confirmation status, schema version, notes, and metadata JSONB.

Missing observation != zero != false.

Use relational columns for identity/lifecycle/time/source/common query keys and validated JSONB for type-specific extension payloads.

Subtype areas include `profile_items`, `observations`, `events`, `regimens`, `goals`, `plans`, `contexts`, `tracker_definitions`, `experiments`, `derived_signals`, `insights`, `recommendations`, `records`, `health_relationships`, and `action_proposals`.

Quantities store value plus unit. Provenance distinguishes manual, confirmed, device imported, document/provider imported, AI extracted/derived, and system computed. AI inference never silently becomes a confirmed fact.

Device retention preserves useful low-frequency samples while leaving high-frequency raw streams in HealthKit/external sources unless a feature requires them.

## Phase 1 Profile v1 contract

Phase 1 registers only `profile_item` schema version 1. Its payload has `kind`, `category`, stable lower-case `key`, display `label`, and a required `value`. A JSON `null` value means unknown. Tagged values are `text`, `boolean`, finite `number`, finite `quantity` with a supported unit, and a bounded `text_list`. `false` and `0` remain known values. Extra payload fields and unregistered type/version pairs are rejected. Category and kind must agree: fact/background, constraint/constraints, preference/preferences.

Profile validity instants must include an offset and are normalized to UTC. Windows are half-open `[valid_from, valid_to)`; either bound may be absent, and two supplied bounds must be ordered. Recorded/created/updated times describe when Health knew the item. They do not replace effective validity. Manual structured saves are `user_confirmed`; provenance remains a separate source field. `ai_use_allowed` and `cross_domain_use_allowed` both default to false. Phase 1 stores only bounded display metadata, not unvalidated health payloads.

The schema registry is additive: a later payload version gets a new `(object_type, schema_version)` entry and a migration/conversion policy that keeps old revision snapshots readable. Existing registered versions are immutable. Phase 1 does not register event, observation, regimen, or other later-phase schemas.
