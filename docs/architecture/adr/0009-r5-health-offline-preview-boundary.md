# 0009. R5 Health offline preview boundary

**Disposition** — The owners' C1–C3 design direction supports an offline Health slice. The product transport, enrollment, receipt and recovery contracts remain gated.

## C1 identity and transport

The reviewed Health mobile host uses Firebase email/password. A host that can obtain direct Google human proof for the registered PAS audience has yet to be demonstrated. The separate-process feasibility witness also supplies callback routing and live Health request custody through private test pipes. Product routing must reach the initiating Health worker while its current request context is available and independently authenticate PAS. Matching email, a service token alone, and the narrow delegated federation assertion confer no R5 authority. The existing Firebase verifier and active owner lookup remain the intended Health identity boundary.

There is no R5 HTTP route or provider client. The local source and journal require both the broad read gate and the default-off `PERSONAL_AI_R5_PREVIEW_ENABLED` gate in `APP_ENV=test` with Firebase settings. Current authority is supplied only through an internal seam exercised with synthetic tests. Real activation needs approved host/audience registration, verified linked-provider and deterministic existing-owner enrollment, routing/custody, freshness, nonce replay ownership, and revocation behavior. Unavailable authority terminates the operation.

## C2 source

The offline fixture uses the existing `health-context-read-v1` profile operation with one `profile_item` from `profile_preferences`, exactly `record` and one result. It uses the literal key `r5_synthetic_presentation_format`, label `Synthetic presentation format` and value `{"type":"text","value":"bullets"}`. The synthetic fixture is a manual, user-confirmed input. Health independently checks the selected UID and existing active local owner, exact record and revision, both consent bits and temporal validity, field sensitivity and source fingerprint. The same entity's current permission version must match the projection. This test fixture describes the local allowlist. The exact production literals and PAS source, branch, memory, runtime and recipient authority remain joint contracts.

## C3 reservations and receipts

An append-only PostgreSQL table reserves two distinct original keys in one transaction for each immutable bound intent. The fixed title is included in the local binding digest, along with scope, enrollment, actor, client, installation, selection, permission version, branch and intended destination. The journal contains selected identifiers, scopes represented by digests, the synthetic create request digest and timestamps. It participates in owner export and the existing write freeze and erasure. The preview request digest awaits the original verified PAS create result. The local digest encoding has no wire authority.

A missing response leaves the reservation unresolved. There is no API for posting, adopting a success, or reusing a restored row as live authority. Separate create and preview PAS receipt purposes, signature and digest vectors, key custody/rotation/revocation and original-key GET recovery are prerequisites to enabling any of those effects. Status and recovery also need current reauthorization and an independent generation outside the restored failure domain. The Health-only slice provides no independent anti-rollback witness.

## Rollback

Keep the R5 preview gate false and retain existing owner export and erasure. The additive migration refuses downgrade while reservations exist. Mobile awaits paired evidence. Bound continuation and dispatch remain under the existing PAS/R4 hold.
