# Security and privacy baseline

This is a personal project, not a claim of formal HIPAA compliance. Health data receives strong privacy-by-default treatment.

Baseline: no DB credentials on clients; TLS; private object storage; short-lived signed URLs; opaque object keys; separated environments; least privilege; per-user ownership checks; no routine logging of sensitive health payloads; export/deletion before maturity.

Phase 9 adds a no-store owner JSON export with repeatable-read consistency and
row/byte bounds. Domain deletion requires explicit confirmation and, in
Firebase mode, a verified token with `auth_time` no older than five minutes.
The request commits an owner write freeze before it removes private object
generations and relational history/import/proposal data. A health-free owner
marker and Firebase subject mapping remain as inputs for a future restore
replay step. The marker alone does not stop an older database backup from
restoring deleted data; no restore pipeline exists. Domain deletion does not
remove a Firebase identity, Apple HealthKit originals, or external Personal AI
copies.

Health objects should be designed for AI-use and future cross-domain-use permissions. Distinguish user-entered, imported, extracted, and derived information.

The future web client follows the same rule: no direct Neon access from browser code and no bypass of the Health API authorization boundary.

`APP_ENV` is exactly `local`, `test`, or `cloud`. Only local and test may use `AUTH_MODE=dev`; its sole identity comes from server-only `LOCAL_PRINCIPAL_ID`, and protected routes return 401 when it is absent. Cloud requires Firebase bearer verification and rejects any configured local principal. Missing, malformed, expired, revoked, wrong-project, or disabled-user tokens fail closed with 401. Firebase key-fetch or revocation-service outages return a sanitized 503 and never fall back to development identity.

The cloud API verifies Firebase ID-token signature, issuer, audience, expiry, and revocation through the Admin SDK with a four-second per-request network timeout and a bounded in-flight verifier gate. Firebase's SDK caches public signing certificates according to cache headers; revocation is checked against Firebase for every authenticated request rather than cached locally. Invalid, expired, revoked, disabled or deleted-account tokens return 401; certificate and revocation service outages return sanitized 503. The bearer token's verified `(issuer, subject)` maps to a stable internal UUID in the additive `provider_identities` table. Email is not part of identity matching, and first login never attaches to or merges a local development principal. An owner migration requires a separately documented, owner-verified process and is not included here.

The mobile SDK owns persisted Firebase session state and refreshes ID tokens before use. Tokens are sent only in HTTPS `Authorization: Bearer` headers. They never enter API URLs or routine logs. An account switch or sign-out remounts the routed UI and clears the app's in-memory uncertain-save records; there is no persistent health-data cache in this release. Cloud project identifiers and Firebase client configuration are public deployment inputs; Firebase service-account keys and database URLs are server-side secrets and are not embedded in the mobile bundle.

Cloud config requires a private GCS bucket, a pooled runtime Neon endpoint with `sslmode=verify-full`, a separate direct `MIGRATION_DATABASE_URL`, and an explicit API connection budget. The app uses one worker, five connections per instance, zero overflow, and a maximum one-second pool checkout and connection-establishment timeout. Idle pooled connections receive a one-second PostgreSQL statement timeout for pre-ping; checkout overrides that idle-only limit to zero for the current transaction, so domain query behavior remains governed by its existing application policy. `/readyz` applies a one-second transaction-local statement timeout to its read-only `SELECT 1`; a checked-out connection is rolled back and released on timeout. These database bounds fit inside Terraform's five-second startup/readiness probe envelope, including a replacement connection. Database and object-storage credentials never appear in API errors or OpenAPI. `/healthz` remains process liveness; `/readyz` returns only generic canonical database availability and no connection details. Interactive API documentation is disabled in cloud.

These controls are a private product security baseline, not a claim of formal HIPAA compliance. Cloud identity, connection, GCS IAM, billing, and restore behavior remain unverified until a user-supplied staging environment is deployed.

## AI data controls

Every health object defaults to `ai_use_allowed=false`. Profile, planning, and
daily Event/Observation forms expose the item-level choice; daily permission
updates create ordinary revision snapshots. Context and search recheck owner,
active/current status, temporal validity and item permission on each request.
The separate cross-domain flag does not grant Personal AI access. Context is
bounded to 100 entries and 65,536 serialized bytes; daily history and
unconsented objects are not included. Search has a 90-day daily-entry window
and bounded pages.

Do not send health data to an AI provider unless its service identity,
delegation, tool registration, retention, and safety contracts are supplied
and reviewed. Until then, the provider adapter must remain disabled and
configuration must reject activation. See [current state](../current-state.md)
for the current provider status and [Phase 5 evidence](../implementation/evidence/phase-5-release.md)
for the checks and remaining gates.
