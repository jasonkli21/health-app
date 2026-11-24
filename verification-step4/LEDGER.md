# PAS and Health paired verification ledger

PAS `00c7d954f864d001ec7186c5c98528262abbf06d`

Health `dff958671ae637198a90c1091c43228e4808bcb3`

| Row | Paired verdict | Evidence |
|---|---|---|
| H08 | PASS E1 synthetic | Original Health R5 create/preview and private dispatch receipts verified. One synthetic Health profile preference and separately authorized canonical PAS memory were present in exactly one fixture-observed POST with the attested digest. |
| H09 | PASS E1 synthetic | Each crossed authority, consent, epoch, owner, record, and PAS grant case issued and received zero provider POSTs. A Health source revoked at the second send check was blocked after both runtime fences and before the socket write. |
| H10 | PASS E1 synthetic with named native stores | Concurrent same-key Health calls and a lost 202 each produced one POST. Receiver 429, read timeout and EOF each produced one POST and a nonterminal original-key read with no resend. Pre-write interruptions at three layers produced zero POSTs. Full independent process restore remains unverified. |
| H11 | PASS E1 synthetic with named native stores | Current Health and PAS rights gate status and matching detail. Valid recovery verifies the pinned terminal and exact result before disclosure. Crossed keys/owners, Health or PAS revoke, conflicting detail, forged terminal and expiry at publication suppress disclosure. |
| H17 | PASS E1 synthetic topology | Separate Health, PAS and fake receiver processes and loopback ports. Native Health profile/intent and PAS principal/memory/routing root, POSIX send fences, PAS fixture canonical SQLite and synthetic grant/dependency/branch witnesses. Full native/independent restore and hosted tiers remain unverified. |

| Scenario | Caller continuation POSTs to PAS | PAS POSTs issued | Receiver POSTs | PAS journal | Native root | Runtime fences | Health outward result |
|---|---:|---:|---:|---|---|---:|---|
| ok | 1 | 1 | 1 | completed | yes | 2 | verified result |
| concurrent | 1 | 1 | 1 | completed | yes | 2 | verified result |
| lost-ack | 1 | 1 | 1 | completed | yes | 2 | verified result |
| 429 | 1 | 1 | 1 | send_started | yes | 2 | none |
| timeout | 1 | 1 | 1 | send_started | yes | 2 | none |
| disconnect | 1 | 1 | 1 | send_started | yes | 2 | none |
| changed-detail | 1 | 1 | 1 | completed | yes | 2 | none |
| expired-before-publication | 1 | 1 | 1 | completed | yes | 2 | none |
| health-ai-consent | 0 | 0 | 0 | unknown | no | 0 | none |
| health-cross-domain-consent | 0 | 0 | 0 | unknown | no | 0 | none |
| health-owner | 0 | 0 | 0 | unknown | no | 0 | none |
| health-firebase-revoked | 0 | 0 | 0 | unknown | no | 0 | none |
| health-record | 0 | 0 | 0 | unknown | no | 0 | none |
| health-recipient | 0 | 0 | 0 | unknown | no | 0 | none |
| health-crossed-recipient | 0 | 0 | 0 | unknown | no | 0 | none |
| crossed-pas-owner | 0 | 0 | 0 | unknown | no | 0 | none |
| regrant-higher-epoch | 0 | 0 | 0 | unknown | no | 0 | none |
| pas-memory | 1 | 0 | 0 | unknown | no | 0 | none |
| pas-source | 1 | 0 | 0 | unknown | no | 0 | none |
| pas-owner | 1 | 0 | 0 | unknown | no | 0 | none |
| pas-release | 1 | 0 | 0 | unknown | no | 0 | none |
| interrupt-after-health-commit | 0 | 0 | 0 | unknown | no | 0 | none |
| pas-root-failure | 1 | 0 | 0 | claimed | no | 0 | none |
| pas-after-fence | 1 | 0 | 0 | send_started | yes | 2 | none |
| health-revoked-after-fence | 1 | 0 | 0 | send_started | yes | 2 | none |
| forged-terminal | 1 | 1 | 1 | completed | yes | 2 | none |

Across 26 scenarios, PAS issued 9 provider POSTs and the independent receivers observed the same count. Each issued POST matched the corresponding receiver digest and pre-confirmation preview attestation. Distinct original attempts were used across scenarios.

The JSONL records come from successive runs and four supplemental fault cases. The initial Firebase stub omitted `UserNotFoundError` and the first crossed-owner probe expected the empty read response on a POST. The corrected probes exercised the reviewed verifier and private admission and recorded zero provider POSTs.

E2 evidence applies only to the named native stores in this fixture. Full independent restore, hosted identity and enrollment, installed/mobile runtime and production activation remain outside this paired verdict. No Step 5 release or activation occurred.
