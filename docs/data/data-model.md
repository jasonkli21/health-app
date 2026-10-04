# Logical data model

The model supports structured common health concepts, custom user-defined information, temporal correctness, provenance, confirmation status, sparse tracking, and longitudinal analysis.

Core vocabulary: Fact/profile item, Constraint, Preference, Regimen, Goal, Plan, Active context, Event, Observation, Tracker definition, Experiment, Derived signal, Insight, Recommendation, Record, Relationship, Action proposal.

A common `health_objects` envelope should include identity, user, object type/domain/status, title, validity window, recorded/created/updated times, source, confirmation status, schema version, notes, and metadata JSONB.

Missing observation != zero != false.

Use relational columns for identity/lifecycle/time/source/common query keys and validated JSONB for type-specific extension payloads.

Subtype areas include `profile_items`, `observations`, `events`, `regimens`, `goals`, `plans`, `contexts`, `tracker_definitions`, `experiments`, `derived_signals`, `insights`, `recommendations`, `records`, `health_relationships`, and `action_proposals`.

Quantities store value plus unit. Provenance distinguishes manual, confirmed, device imported, document/provider imported, AI extracted/derived, and system computed. AI inference never silently becomes a confirmed fact.

Device retention preserves useful low-frequency samples while leaving high-frequency raw streams in HealthKit/external sources unless a feature requires them.
