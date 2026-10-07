# Phase 9 implementation evidence — local account-data foundation

Updated October 7, 2026. This record describes the Phase 9 work delivered in
the local repository. It is implementation evidence, not Phase 9 acceptance or
a production release sign-off.

## Delivered

- `GET /exports/current` returns a versioned `personal-health-owner-export-v1`
  JSON snapshot from one PostgreSQL repeatable-read transaction. Its explicit
  inventory covers the 25 current health-domain owner tables, emits a row-count
  manifest, and caps output at 100,000 rows and 20 MiB. Internal deletion-job
  state and the erasure ledger are excluded. Serialization is
  incremental and the response is `no-store`. The manifest states that record
  files are omitted because record ingress is not enabled. The mobile “Your
  data” screen opens the owner snapshot in the platform share sheet; the
  receiving app controls any copy it retains.
- `POST /deletion-requests` requires the exact
  `DELETE MY HEALTH DATA` confirmation and a client request UUID. Firebase
  requests require a verified `auth_time` no older than five minutes; local
  development uses its server-configured principal. The mobile screen stores
  the request UUID securely and can continue the same request after a timeout
  or restart. `GET /deletion-requests/{request_id}` exposes only its state,
  timestamps, and a fixed error code.
- The request commits `users.lifecycle = deleting` before erasure. Database
  triggers on every current owner-scoped table lock the owner row and reject
  inserts/updates unless the owner is active. Cleanup removes at most 1,000
  object generations per request step and at most 10,000 relational rows per
  request, with relational transactions capped at 1,000 rows. The same request
  UUID resumes pending or failed work. Relational cleanup follows reverse
  foreign-key order and includes proposal receipts/history, analytics evidence,
  HealthKit import receipts/identities/preferences, planning history, sources,
  and canonical object history.
- The owner row and Firebase subject mapping remain with an erased lifecycle;
  timezone and daily sequence are reset. `owner_erasure_ledger` retains only
  the owner UUID and erasure time as input for a future isolated restore-replay
  step. No replay runner exists, so the marker alone does not prevent an older
  database backup from resurrecting an erased owner. Its expiry is unset while
  actual backup retention and restore behavior are unknown. The
  mobile flow clears per-account secure consent and indexed checkpoints after
  server completion, then signs out. The current build has no native HealthKit
  adapter writing checkpoints.

## Reconciled scope and disabled capabilities

The implementation has no document-record or extraction routes, migrations,
or mobile Records review surface. File ingress remains disabled because there
is no malware scanner/quarantine provider or isolated parser policy. Lab
extraction remains disabled because Personal AI is disabled and no reviewed
extraction identity, protocol, accuracy, or retention contract exists. No lab
command was added to the Phase 6 proposal registry.

Large exports that exceed the synchronous bounds are rejected; a durable
export task and temporary private download are still required. Deletion
processing is request-driven rather than a background worker. No encrypted
portable backup, isolated restore, deletion-ledger replay tool, actual RPO/RTO
measurement, record-file cleanup drill, full-system performance dataset,
dependency/security audit, or end-to-end release walkthrough was completed.
No live Neon, GCS, Firebase reauthentication, external Personal AI retention,
or device behavior is certified here. The retained Firebase identity and
erased lifecycle prevent silent reenrollment in the current database; a fresh
domain-principal flow is not implemented. No restore workflow currently
replays the ledger, so restoration from an older database backup could
resurrect erased data. `infra/gcp` plans a private bucket with uniform access
and public-access prevention, but no live bucket, object versioning/retention
policy, or Neon backup policy has been configured or verified.

## Checks performed

| Check                                                             | Result                                                                                                                                                               | Limit                                                                                               |
| ----------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Ruff check and formatting on changed Python sources and migration | Passed                                                                                                                                                               | Focused changed-file scope                                                                          |
| Python `compileall` on changed API sources and migration          | Passed                                                                                                                                                               | Syntax/bytecode only                                                                                |
| Alembic heads                                                     | `20261007b1c2`                                                                                                                                                       | Migration graph only                                                                                |
| Alembic `upgrade head --sql`                                      | Passed                                                                                                                                                               | Offline SQL generation; migration was not applied to a live database                                |
| PostgreSQL migration upgrade and `alembic check`                  | Upgraded through `20261007b1c2`; drift check reported no new operations on PostgreSQL 16.15                                                                          | Disposable local PostgreSQL only; PostgreSQL 17 and query plans remain unchecked                    |
| ORM owner-table inventory                                         | 25 health-domain tables; exact match with export/erasure inventory and triggers                                                                                      | Static metadata only                                                                                |
| PostgreSQL account-data behavior                                  | Passed: full owner inventory export/erase, second-owner preservation, row/UTF-8 limits, concurrent repeatable-read snapshot, freeze, recovery, and downgrade refusal | Synthetic fixtures on disposable PostgreSQL 16.15; live provider/object behavior is not established |
| FastAPI OpenAPI export and generated API client                   | Passed                                                                                                                                                               | Contract and generation only                                                                        |
| Mobile TypeScript typecheck                                       | Passed                                                                                                                                                               | Static typing only                                                                                  |
| Full mobile Vitest suite                                          | 125 passed across 25 files                                                                                                                                           | Simulated storage/auth; no native iOS or HealthKit behavior                                         |
| Mobile ESLint on changed screens and adapters                     | Passed                                                                                                                                                               | Focused changed-file scope                                                                          |
| Generated API client strict TypeScript check                      | Passed                                                                                                                                                               | Generated contract typing only                                                                      |
| Prettier on changed docs, contract, and mobile files              | Passed                                                                                                                                                               | Formatting only                                                                                     |
| Relative links in changed Markdown                                | Passed                                                                                                                                                               | Local path existence only; external links and anchors not checked                                   |
| Focused mypy                                                      | Internal error in installed mypy 1.20.2 while reading typeshed `zipimport.pyi`                                                                                       | No source diagnostics were produced                                                                 |
| Full API test suite                                               | 221 passed; one Starlette/httpx deprecation warning                                                                                                                  | PostgreSQL 16.15 disposable database; no PostgreSQL 17, Neon, live GCS, or device claims            |
| Native iOS build/device review                                    | Not run                                                                                                                                                              | Full Xcode and a configured HealthKit development build are unavailable in this evidence            |

Phase 9 remains open. The database-backed results above establish only local
PostgreSQL 16.15 behavior with synthetic fixtures. They do not establish
PostgreSQL 17, GCS, Neon, backup/restore, malware scanning, OCR/extraction
accuracy, or native-device acceptance.
