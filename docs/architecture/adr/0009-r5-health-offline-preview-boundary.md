# 0009. R5 Health offline preview boundary

**Disposition** — The owners' C1–C3 design direction supports an offline Health slice. The product transport, enrollment, receipt and recovery contracts remain gated.

## C1 identity and transport

The reviewed Health mobile host uses Firebase email/password. A host that can obtain direct Google human proof for the registered PAS audience has yet to be demonstrated. The separate-process feasibility witness also supplies callback routing and live Health request custody through private test pipes. Product routing must reach the initiating Health worker while its current request context is available and independently authenticate PAS. Matching email, a service token alone, and the narrow delegated federation assertion confer no R5 authority. The existing Firebase verifier and active owner lookup remain the intended Health identity boundary.

There is no R5 HTTP route or provider client. The local source and journal require both the broad read gate and the default-off `PERSONAL_AI_R5_PREVIEW_ENABLED` gate in `APP_ENV=test` with Firebase settings. Current authority is supplied only through an internal seam exercised with synthetic tests. Real activation needs approved host/audience registration, verified linked-provider and deterministic existing-owner enrollment, routing/custody, freshness, nonce replay ownership, and revocation behavior. Unavailable authority terminates the operation.

## C2 source

The offline fixture uses the existing `health-context-read-v1` profile operation with one `profile_item` from `profile_preferences`, exactly `record` and one result. It uses the literal key `r5_synthetic_presentation_format`, label `Synthetic presentation format` and value `{"type":"text","value":"bullets"}`. The synthetic fixture is a manual, user-confirmed input. Health independently checks the selected UID and existing active local owner, exact record and revision, both consent bits and temporal validity, field sensitivity and source fingerprint. The same entity's current permission version must match the projection. This test fixture describes the local allowlist. The exact production literals and PAS source, branch, memory, runtime and recipient authority remain joint contracts.

## C3 reservations and receipts

PostgreSQL reserves both original keys atomically. Exact wire callers bind the existing opaque PAS principal, registered client, enrollment, selected record, branch and destination. The create request uses the fixed title and the reserved key before its canonical request digest is committed. The earlier UUID-only reservation format remains readable for unshipped fixtures. It cannot be upgraded into a wire binding.

Health verifies a detached, bounded Ed25519 create receipt against the committed binding and exact response before committing the final preview digest and conversation. A second prepare of that original preview is refused. After reservation and binding commit, the caller rechecks the exact source and full intent before releasing prepared data. The isolated transport repeats this check before POST. This check and transport do not serialize native source writers. Ambiguous delivery can only be observed through original-key GET. Health checks source and journal authority before and after the call, compares independent immutable branch, destination and grant snapshots and returns only metadata verified in the signed response. An unavailable independent current-authority witness, legacy binding, changed authority or missing result leaves the operation unresolved. The fixture supplies its ephemeral signer and expected current epochs. Hosted key issuance, rotation, retention and a durable independent generation authority remain open. The journal retains no receipt bytes, prompts, values or tokens. Account export, write freeze and erasure include exact bindings.

## Rollback

Keep the R5 preview gate false and retain existing owner export and erasure. The additive migration refuses downgrade while reservations exist. The isolated mobile observer uses an in-memory selection lifetime. Bound continuation and dispatch remain under the existing PAS/R4 hold.
