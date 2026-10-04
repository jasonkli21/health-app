# Persistence layer

`models.py` defines only the six Phase 1 PostgreSQL tables: `users`, `sources`,
`health_objects`, `profile_items`, `health_object_revisions`, and
`health_relationships`. JSON health payloads use PostgreSQL JSONB and are
validated through the domain schema registry before writes. Composite foreign
keys include `owner_id` for source, subtype, revision, and relationship edges;
application queries also require the resolved principal.

`database.py` creates request-scoped synchronous SQLAlchemy sessions. Schema
changes are performed only by root Alembic migrations. SQL echo is off so bound
health values do not reach routine logs. Keep additional query/use-case rules in
the application layer and add new subtype tables only in their owning phase.
