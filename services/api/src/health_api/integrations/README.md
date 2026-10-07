# Integrations

Adapters for Personal AI, object storage, authentication, and later HealthKit/import sources. External systems must not leak transport-specific concerns into the domain layer.

The Personal AI adapter is a typed, disabled boundary until its real service,
service-to-service identity, user delegation, tool callback, timeout, and
retention contracts are reviewed. Do not add a guessed endpoint, accept an
arbitrary URL, or forward a user bearer token to a model provider. Health
context must be rebuilt immediately before any future send; provider evidence
must resolve to included owner revisions.

## Object storage boundary

`object_storage.py` exposes only owner-scoped put/get/delete operations with
opaque UUID object IDs, validated media types, a configured byte limit, and
sanitized failure types. Local storage uses owner-namespaced directories,
dirfd-relative no-follow operations, restrictive permissions, and a small
metadata header. GCS uses the same owner prefix, generation preconditions to
prevent overwrite/delete races, bounded timeouts, and no automatic retries.
Never derive a path or key from an uploaded filename or accept an owner ID from
untrusted request data.

These adapters do not constitute a document-record or upload API. Real
health-file ingress requires verified owner authentication, a private cloud
bucket, validation/quarantine, retention policy, and a reviewable record
lifecycle before a product route is enabled. Use synthetic payloads in
[object-storage tests](../../../tests/test_object_storage.py); do not put
real health documents in fixtures or logs.
