# ADR 0008: Phase 4 planning, schedules, and custom trackers

- **Status:** Accepted for Phase 4 implementation
- **Date:** 2026-10-05
- **Context:** The Phase 4 plan predates the delivered Phase 1–3 model. The
  current API stores Profile, Event, and Observation in the owner-scoped
  `health_objects` envelope with immutable revision snapshots and relational
  subtype tables. The envelope currently limits object types, domains, and
  schema versions to those delivered capabilities. Existing Observations have
  typed metrics used by Phase 2 Today rollups.

## Decision

Phase 4 extends the canonical store rather than introducing another database or
generic object API. New planning subtypes, plan items, schedule versions,
occurrence overrides, and tracker definition versions use composite
owner-consistent references. Writes use the existing manual source, explicit
user confirmation, envelope revision, idempotency, owner resolution, and
`health_object_revisions` history.

The envelope status remains `active` or `archived`. Each planning subtype owns
its typed lifecycle (`active`, `paused`, `completed`, `ended`, as appropriate),
which is included in history snapshots. Context validity controls its presence
in Today and never modifies Profile or regimen state. Resource relationships
are validated against owner and expected subtype before commit.

Schedules are versioned intent. Expansion is an API read over at most 31 local
dates and 500 results. A slot key is derived from its stable schedule identity
and original local date/time, not its revision. Editing a schedule creates a
new version effective on an explicit local date. Past slots keep their prior
override/history. Local-time conversion resolves a spring gap to the next valid
time and a fall overlap to the earlier offset. An occurrence action records an
explicit user assertion; it does not create a health observation or infer
adherence.

Custom tracker definitions have bounded primitive fields and immutable schema
versions. Tracker entries are typed Observation payload variants that point to
an owner definition version. They are decoded against that historical version
and remain separate from existing measurement metrics unless a later explicit
metric mapping is added. No executable field logic, arbitrary JSON Schema, or
AI-generated definition is introduced.

Today keeps existing daily items, summary calculations, sequence snapshots,
and paging semantics. Phase 4 adds `plan_items` and `active_contexts` to the
response without altering daily rollups. Missing occurrence actions remain
unknown, not missed.

## Consequences

- Alembic expands the envelope allowlists and creates additive owner-scoped
  tables; historical Phase 1–3 payloads and daily revisions remain readable.
- Schema-history references are retained when a tracker or schedule is
  archived. Definition edits append versions rather than rewriting old entries.
- PostgreSQL migration lifecycle, query plans, cloud auth parity, and mobile
  device/DST presentation remain release gates and must be reported separately
  from local source implementation.

