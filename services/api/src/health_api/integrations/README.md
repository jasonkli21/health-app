# Integrations

Adapters for object storage, authentication, and later HealthKit/import
sources. External systems must not leak transport-specific concerns into the
domain layer.

The Personal AI integration has a separate, default-off
`health-context-read-v1` route at `/v1/integrations/personal-ai/context`.
`personal_ai_context.py` owns the strict versioned DTO, and
`personal_ai_context_auth.py` verifies a Google service identity and a recent,
revoked-checked Firebase owner identity before Health lookup. The projection
uses Health's canonical read permissions and remains separate from
`AIContextPack`. The route does not enable `/assistant/status` or
`POST /assistant/messages`; the latter remains a sanitized 503 and
`PERSONAL_AI_ENABLED` remains rejected. The Personal AI repository currently
provides Google OIDC user tokens rather than delegated Firebase tokens, so
live reads between the repositories remain unavailable. Do not add a guessed
identity mapping, accept an arbitrary URL, or forward a user bearer token to a
model provider.

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

Phase 9 adds owner-prefix cleanup for erasure. It removes only opaque `.blob`
objects under the configured owner's namespace, uses GCS generation
preconditions, includes noncurrent GCS generations, and handles at most 1,000
objects per call. A larger namespace or storage failure leaves the deletion job
retryable; the API does not report completion before object cleanup succeeds.
