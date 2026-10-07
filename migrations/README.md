# Database migrations

Alembic is the only schema creation/update path. The root `alembic.ini`, this
environment, and immutable revisions under `versions/` are authoritative. The
initial Phase 1 revision is `22dad79c2ee1`; Phase 4 extends the same canonical
store at `d4e5f607a8b9` with planning, schedules, occurrence actions, tracker
schema versions, and custom Observation columns. Review corrections follow at
`a7f014edc620`; `b8a125fec731` allows retired scheduled manual tasks to retain
their NULL reference target. Phase 5 adds full-text retrieval indexes at
`f5c0a1e2d3b4`. The Phase 6 proposal store was added at `e7f6a5b4c3d2` on
the planning migration branch. `20261006b1a2` merges both histories and drops
the per-proposal-revision receipt uniqueness constraint so each accepted retry
key can bind to the one canonical applied result. Phase 7 revision
`f7c8d9e0a1b2` adds analytics artifact/evidence storage. Phase 8 revision
`c8d9e0f1a2b3` adds bounded HealthKit batch receipts, source identities,
aggregate source preferences, and additive Observation metrics. Follow-up
revision `20261007a0b1` adds bounded aggregate source revisions, deletion
identities without fabricated health objects, user-archive protection, and
step bounds/date-only checks; it is the current head. The Phase 8 downgrade
refuses when imported identities, batch history, or unrepresentable aggregate
revision state exists. Phase 7 downgrade refuses when alternate receipt keys
have already been accepted for one proposal revision.
The API never calls `metadata.create_all()` and never runs migrations during a
request or startup.

Run from the repository root after starting local PostgreSQL and installing the
API package:

```bash
.venv/bin/alembic upgrade head
.venv/bin/alembic current
.venv/bin/alembic check
```

`DATABASE_URL` is loaded from the server-only `.env` or process environment.
Use `alembic downgrade base` only against an empty disposable database; it drops
all application tables and data. The Phase 4 downgrade refuses to proceed when
planning resources or custom tracker observations exist, because their history
requires a compatible application image or backup restore. Tests require a separate database named
with `test` or `phase1` and may truncate it. Never point `TEST_DATABASE_URL` at
personal data.
