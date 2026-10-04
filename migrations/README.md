# Database migrations

Alembic is the only schema creation/update path. The root `alembic.ini`, this
environment, and immutable revisions under `versions/` are authoritative. The
initial Phase 1 revision is `22dad79c2ee1`; it creates the six Profile tables.
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
the Phase 1 tables and all data in them. Tests require a separate database named
with `test` or `phase1` and may truncate it. Never point `TEST_DATABASE_URL` at
personal data.
