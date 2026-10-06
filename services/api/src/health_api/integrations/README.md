# Integrations

Adapters for Personal AI, object storage, authentication, and later HealthKit/import sources. External systems must not leak transport-specific concerns into the domain layer.

The Personal AI adapter is a typed, disabled boundary until its real service,
service-to-service identity, user delegation, tool callback, timeout, and
retention contracts are reviewed. Do not add a guessed endpoint, accept an
arbitrary URL, or forward a user bearer token to a model provider. Health
context must be rebuilt immediately before any future send; provider evidence
must resolve to included owner revisions.
