# Containers

`docker-compose.yml` at the repository root starts only the local PostgreSQL
dependency. Ordinary development does not require cloud resources.

`api.Dockerfile` builds the production API image from the repository root. It
installs only `services/api/requirements-runtime.lock` with hash checking,
copies the API and Alembic migration sources, runs as UID/GID 10001, and serves
the injected `PORT` with one worker. The local storage directory is created
with owner-only permissions; cloud mode uses workload identity and private
GCS instead. Build context exclusions live in the root `.dockerignore`.

The image also serves as the separate Alembic Cloud Run Job image by overriding
the command. It never runs migrations in the web-server startup path. Docker
and Podman were unavailable on the implementation host, so image build, scan
and local container execution remain unverified; see the Phase 3 release
evidence and GCP runbook.
