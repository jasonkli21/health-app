# Security and privacy baseline

This is a personal project, not a claim of formal HIPAA compliance. Health data receives strong privacy-by-default treatment.

Baseline: no DB credentials on clients; TLS; private object storage; short-lived signed URLs; opaque object keys; separated environments; least privilege; per-user ownership checks; no routine logging of sensitive health payloads; export/deletion before maturity.

Health objects should be designed for AI-use and future cross-domain-use permissions. Distinguish user-entered, imported, extracted, and derived information.

The future web client follows the same rule: no direct Neon access from browser code and no bypass of the Health API authorization boundary.

`APP_ENV` is exactly `local`, `test`, or `cloud`. Only local and test may use `AUTH_MODE=dev`; its sole identity comes from server-only `LOCAL_PRINCIPAL_ID`, and protected routes return 401 when it is absent. Cloud requires Firebase bearer verification and rejects any configured local principal. Missing, malformed, expired, revoked, wrong-project, or disabled-user tokens fail closed with 401. Firebase key-fetch or revocation-service outages return a sanitized 503 and never fall back to development identity.

The cloud API verifies Firebase ID-token signature, issuer, audience, expiry, and revocation through the Admin SDK with a four-second per-request network timeout and a bounded in-flight verifier gate. Firebase's SDK caches public signing certificates according to cache headers; revocation is checked against Firebase for every authenticated request rather than cached locally. Invalid, expired, revoked, disabled or deleted-account tokens return 401; certificate and revocation service outages return sanitized 503. The bearer token's verified `(issuer, subject)` maps to a stable internal UUID in the additive `provider_identities` table. Email is not part of identity matching, and first login never attaches to or merges a local development principal. An owner migration requires a separately documented, owner-verified process and is not included here.

The mobile SDK owns persisted Firebase session state and refreshes ID tokens before use. Tokens are sent only in HTTPS `Authorization: Bearer` headers. They never enter API URLs or routine logs. An account switch or sign-out remounts the routed UI and clears the app's in-memory uncertain-save records; there is no persistent health-data cache in this release. Cloud project identifiers and Firebase client configuration are public deployment inputs; Firebase service-account keys and database URLs are server-side secrets and are not embedded in the mobile bundle.

Cloud config requires a private GCS bucket, a pooled runtime Neon endpoint with `sslmode=verify-full`, a separate direct `MIGRATION_DATABASE_URL`, and an explicit API connection budget. The app uses one worker, five connections per instance, zero overflow and a short pool/connect timeout by default. The budget reserves `2 × maximum instances × per-instance SQLAlchemy pool capacity` to account for old and new Cloud Run revisions overlapping during rollout. Database and object-storage credentials never appear in API errors or OpenAPI. `/healthz` remains process liveness; interactive API documentation is disabled in cloud.

These controls are a private product security baseline, not a claim of formal HIPAA compliance. Cloud identity, connection, GCS IAM, billing, and restore behavior remain unverified until a user-supplied staging environment is deployed.
