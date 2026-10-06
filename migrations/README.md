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
key can bind to the one canonical applied result. This is the current head.
Its downgrade refuses when alternate receipt keys have already been accepted
for one proposal revision.
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
