# Security and privacy baseline

This is a personal project, not a claim of formal HIPAA compliance. Health data receives strong privacy-by-default treatment.

Baseline: no DB credentials on clients; TLS; private object storage; short-lived signed URLs; opaque object keys; separated environments; least privilege; per-user ownership checks; no routine logging of sensitive health payloads; export/deletion before maturity.

Health objects should be designed for AI-use and future cross-domain-use permissions. Distinguish user-entered, imported, extracted, and derived information.

The future web client follows the same rule: no direct Neon access from browser code and no bypass of the Health API authorization boundary.
