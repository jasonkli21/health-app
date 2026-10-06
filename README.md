# Personal Health

A mobile-first personal health application for maintaining a structured, extensible health record across profile information, daily observations, goals, plans, schedules, and custom trackers.

The Health app owns canonical health state. A separate `personal-ai-system` is the intended boundary for reusable model orchestration, research, and cross-domain AI reasoning.

## What it does

The application is designed around a flexible personal-health model rather than a fixed questionnaire or a single-purpose tracker.

Current product surfaces support:

- structured personal health profile data;
- versioned profile history and owner-scoped persistence;
- daily health events and observations;
- Today-oriented logging and summaries;
- goals, plans, and schedules;
- custom trackers;
- time-aware and nullable health values;
- mobile-first workflows;
- generated API contracts for the mobile client;
- Firebase-compatible cloud identity boundaries;
- local and cloud object-storage abstractions;
- an explicit integration boundary for future AI-assisted insights and recommendations.

The broader product model is designed to represent nutrition, exercise, sleep, symptoms, measurements, medications/supplements, habits, goals, active contexts, and individualized trackers without treating missing data as false or zero.

## Design principles

- **Structured by default, extensible by design.**
- **Missing data is unknown, not implicitly false or zero.**
- **Time is first-class.**
- **Profile state and daily state are different concepts.**
- **Temporary context can override baseline context.**
- **Canonical health state belongs to the Health app.**
- **AI assistance should remain explainable and user-controlled.**
- **Mobile comes first, but the backend should support a future web client.**

## Architecture

```text
                   React Native / Expo
                         mobile app
                             |
                             | generated typed API client
                             v
                  +----------------------+
                  | FastAPI health API   |
                  |                      |
                  | auth / owner scope   |
                  | profile + daily      |
                  | planning + trackers  |
                  | object metadata      |
                  +----+------------+----+
                       |            |
                       |            +---- typed HTTP ----> personal-ai-system
                       |
                       v
                  PostgreSQL / Neon
                       |
                       +-----------------> object storage
                                          local filesystem
                                          or private GCS
```

### Ownership boundaries

**Mobile application**

- owns interaction and presentation state;
- consumes the generated API client;
- never receives database credentials;
- never supplies trusted owner IDs.

**Health API**

- owns validation, canonical health state, and owner scoping;
- verifies authentication in cloud mode;
- owns persistence and object-storage boundaries;
- exposes the contract used by mobile and a future web client.

**PostgreSQL**

- is authoritative for structured health-domain data;
- uses Alembic for schema changes.

**`personal-ai-system`**

- is an external AI/research boundary;
- should consume explicitly scoped health context rather than becoming the health database.

## Repository layout

```text
.
├── apps/
│   └── mobile/                  # Expo / React Native app
├── services/
│   └── api/                     # FastAPI health service
├── packages/
│   ├── api-client/              # generated TypeScript API client
│   ├── domain/                  # shared health-domain package boundary
│   ├── design-tokens/
│   └── shared/
├── contracts/                   # OpenAPI/shared contract artifacts
├── migrations/                  # Alembic migrations
├── infra/
│   └── gcp/                     # Cloud Run/GCS/Neon Terraform assets
├── scripts/                     # development/release automation
├── docs/                        # product, architecture, security, operations
├── docker-compose.yml
└── package.json
```

A future `apps/web/` client is part of the architecture direction, but the repository is currently mobile-first.

## Tech stack

### Mobile

- React Native
- Expo
- Expo Router
- TypeScript
- pnpm 9.15.0

### API

- Python 3.12
- FastAPI
- Pydantic
- SQLAlchemy 2
- Alembic
- psycopg

### Data / cloud

- PostgreSQL locally
- Neon Postgres in cloud
- local filesystem object storage in development
- private Google Cloud Storage in cloud
- Google Cloud Run
- Firebase Authentication
- Terraform

## Local setup

### Prerequisites

- Python 3.12
- Node.js 22.13+
- pnpm 9.15.0
- Docker / Docker Compose
- Expo Go or Xcode/iOS tooling for mobile execution

### 1. Clone and configure

```bash
git clone https://github.com/jasonkli21/health-app.git
cd health-app

cp .env.example .env
```

The default local configuration uses:

```env
APP_ENV=local
AUTH_MODE=dev
OBJECT_STORAGE_BACKEND=local
DATABASE_URL=postgresql+psycopg://health:health@127.0.0.1:5432/health
PERSONAL_AI_ENABLED=false
```

### 2. Start PostgreSQL

```bash
docker compose up -d postgres
docker compose ps
```

### 3. Install JavaScript dependencies

```bash
corepack enable
corepack prepare pnpm@9.15.0 --activate
pnpm install --frozen-lockfile
```

### 4. Create the Python environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate

python -m pip install \
  -c services/api/requirements-dev.lock \
  -e 'services/api[dev]'
```

### 5. Apply migrations

```bash
.venv/bin/alembic upgrade head
```

The API never auto-creates tables; Alembic owns the schema.

### 6. Start the API

```bash
uvicorn health_api.main:app \
  --reload \
  --app-dir services/api/src \
  --host 127.0.0.1
```

Liveness:

```bash
curl --fail http://127.0.0.1:8000/healthz
```

### 7. Start the mobile app

In another terminal:

```bash
EXPO_PUBLIC_API_URL=http://127.0.0.1:8000 pnpm mobile:start
```

For Android Emulator:

```text
http://10.0.2.2:8000
```

For a physical device, use an approved endpoint reachable only over a trusted/private network. Do not expose the development-auth API directly to the public internet.

## API client generation

FastAPI is the authoritative transport contract.

After API changes:

```bash
pnpm --filter @personal-health/api-client generate
pnpm --filter @personal-health/api-client typecheck
```

Generated artifacts are checked in CI for drift.

## Development checks

With the virtual environment active:

```bash
python scripts/verify_scaffold.py

pytest -c services/api/pyproject.toml services/api/tests

ruff check \
  --config services/api/pyproject.toml \
  services/api/src services/api/tests scripts

ruff format --check \
  --config services/api/pyproject.toml \
  services/api/src services/api/tests scripts

mypy \
  --config-file services/api/pyproject.toml \
  services/api/src scripts

pnpm format:check
pnpm mobile:lint
pnpm mobile:typecheck
pnpm mobile:test
```

For PostgreSQL-backed persistence tests, create a dedicated disposable test database and set `TEST_DATABASE_URL`. The test harness rejects ordinary non-test database names.

## Cloud deployment

The target cloud architecture is:

```text
Expo mobile app
      |
      | Firebase ID token
      v
Cloud Run: health API
   |              |
   |              +--------> private GCS bucket
   |
   +-----------------------> Neon Postgres
```

Infrastructure is defined under `infra/gcp/` with Terraform. It is intentionally reviewable and parameterized; the repository does not contain a preselected GCP project, Firebase project, Neon database, bucket, or billable deployment.

### Cloud prerequisites

Before deployment, provide:

1. a dedicated GCP project;
2. a Firebase Auth project;
3. a region;
4. a globally unique private GCS bucket name;
5. a Neon pooled runtime URL and direct migration URL;
6. Secret Manager secret IDs and numeric versions;
7. an immutable API image digest;
8. approved Cloud Run instance and database connection budgets;
9. a dedicated/versioned Terraform state bucket.

### Cloud runtime settings

Cloud mode requires values equivalent to:

```env
APP_ENV=cloud
AUTH_MODE=firebase
OBJECT_STORAGE_BACKEND=gcs

FIREBASE_PROJECT_ID=...
GCP_PROJECT_ID=...
GCS_BUCKET=...

DATABASE_URL=postgresql+psycopg://...?...sslmode=verify-full
CLOUD_MAX_INSTANCES=...
DATABASE_CONNECTION_BUDGET=...
```

The migration job receives a separate direct Neon URL as:

```env
MIGRATION_DATABASE_URL=...
```

Do not expose either database URL to the mobile app.

### Terraform initialization

Example:

```bash
terraform -chdir=infra/gcp init \
  -backend-config="bucket=OWNER_APPROVED_TERRAFORM_STATE_BUCKET" \
  -backend-config="prefix=personal-health/staging"
```

Then review:

```bash
terraform -chdir=infra/gcp fmt -check
terraform -chdir=infra/gcp validate
terraform -chdir=infra/gcp plan -var-file=release.tfvars
```

Start with the serving API disabled, apply the reviewed infrastructure plan, run the migration job, verify the schema, then deploy the serving revision with a new reviewed plan.

### Build the API image

```bash
scripts/build_cloud_image.sh \
  GCP_PROJECT_ID \
  REGION \
  ARTIFACT_REPOSITORY \
  IMAGE_TAG
```

Resolve the pushed image to an immutable digest before deployment.

### Migrations

Run schema migration separately from service startup:

```bash
gcloud run jobs execute health-api-migrate \
  --project GCP_PROJECT_ID \
  --region REGION \
  --wait
```

The API replicas do not compete to run migrations.

## Authentication

Local development uses a server-side development principal.

Cloud mode uses Firebase Authentication. The mobile app stores Firebase authentication state through the React Native SDK and sends a bearer ID token to the API.

The API derives ownership only from the verified token and server-side identity mapping. It never trusts a client-supplied owner ID or merges identities by email.

## Object storage

Local development stores synthetic/private objects under:

```text
.data/objects
```

Cloud deployment uses a private GCS bucket.

Object-storage limits and timeouts are configured server-side; never place credentials or health data into Expo public environment variables.

## Security notes

- health values and request bodies should not appear in application logs;
- mobile public configuration may contain API/Firebase app identifiers, but never database or server credentials;
- cloud routes require verified Firebase identity;
- object storage stays private;
- database runtime and migration identities are separate;
- schema changes are serialized and explicit;
- health-domain state stays in the Health app rather than the AI platform.

## Documentation

Useful starting points:

```text
docs/project-brief.md
docs/architecture/architecture.md
docs/data/data-model.md
docs/ai/personal-ai-integration.md
docs/local-development.md
infra/gcp/README.md
```

## License

No license is currently specified. Add an explicit `LICENSE` file before treating the repository as generally reusable open-source software.
