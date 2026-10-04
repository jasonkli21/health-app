# Security and privacy baseline

This is a personal project, not a claim of formal HIPAA compliance. Health data receives strong privacy-by-default treatment.

Baseline: no DB credentials on clients; TLS; private object storage; short-lived signed URLs; opaque object keys; separated environments; least privilege; per-user ownership checks; no routine logging of sensitive health payloads; export/deletion before maturity.

Health objects should be designed for AI-use and future cross-domain-use permissions. Distinguish user-entered, imported, extracted, and derived information.

The future web client follows the same rule: no direct Neon access from browser code and no bypass of the Health API authorization boundary.

During Phase 1, only `APP_ENV=local` or `test` can use `AUTH_MODE=dev`. The sole local identity comes from server-only `LOCAL_PRINCIPAL_ID`; request bodies and arbitrary client headers cannot choose an owner. If the ID is unset, protected Profile routes return 401. Unsupported/non-local environments fail settings validation instead of silently enabling development auth. This is a private local development boundary, not internet authentication or a HIPAA compliance claim.
