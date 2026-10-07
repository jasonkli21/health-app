# Phase 9 — Records, reviewed extraction and end-to-end hardening

## Implementation-time reconciliation gate

Check [current state](../../current-state.md) for delivery status and open gates. This plan defines intended scope; it is not evidence of delivery or authorization to begin work. Before implementation or a follow-up, inspect current code, preceding release/review evidence, accepted ADRs and contracts, and external dependencies. Reconcile material drift here before coding.

## User outcome and boundary

**Deliver:** private document records, bounded lab extraction as reviewed proposals, structured imported Observations, provenance/evidence; owner-scoped export, tested backups/restore and deletion; security/integrity/performance/E2E hardening of the entire mobile/backend roadmap.

**Defer:** provider/FHIR ingestion, Garmin/Strava/Oura, advanced nutrition databases/N-of-1 analysis, arbitrary file execution, automatic diagnosis or autonomous medical writes, future web. No detailed W0–W9 plan files. Fix maturity gaps in delivered phases rather than filling deferred products.

## Record lifecycle and storage security

Planned `records` subtype extends canonical envelope: opaque storage key, object generation/version, original display filename (sanitized metadata only), MIME, byte count/hash, uploaded_at, optional document_date/precision, status and extraction linkage. Lifecycle `uploading -> ready|failed`, `ready -> extracting -> review_ready|extraction_failed`, reviewed/imported flags separate from immutable original file; archived/deleting/deleted governed by privacy workflow. No health bytes in DB/logs; owner record/source metadata stays in DB, objects private through Phase 3 adapter.

Initial allowed files: PDF, JPEG, PNG, max20MB/file, max50 PDF pages/extraction, nonzero size. Validate actual signature/decoder plus declared MIME; reject encrypted/password-protected or malformed unsupported files with recoverable explanation, never run embedded actions. Decompression/parse CPU/memory/time bounds; quarantine until validation and appropriate malware scan/isolated parser policy is satisfied. Exact scanner/provider availability is an external gate before real health uploads; absent safe production validation means feature remains disabled, not silently “safe.” Filename never becomes path/key; opaque server-generated owner-contained key. Local parser temporary files deleted on finish/failure, not Cloud Run persistent storage.

Planned `POST /records/uploads` initializes UUID/idempotent upload intent and bounded declared metadata. Local mode uses authenticated streamed API upload; cloud may use tightly scoped short-lived signed PUT/POST if actual GCS supports enforced size/content restrictions, otherwise the same API stream. Credential/signature validity is short (≤5 minutes), method/key-specific, no public ACL. `/records/{id}/finalize` verifies actual object existence/generation/size/hash/type/scan before making ready; mismatch cleans staged object and marks failed. Do not trust mobile-reported hashes alone. Object version/generation precondition prevents finalize racing overwritten objects. `GET /records`, detail and authorized download/view access: owner check before URL issuance, signed GET≤5minutes or local API stream. Signed URL never logged or stored in generic AI context; view authorization rechecked before issuing each URL. Revocation/deletion can't instantly revoke an already issued URL: document this bounded access window, make private-object deletion effective and never claim perfect immediate recall.

DB and object storage are not one transaction. Track upload intents/orphans and explicit state, idempotent finalize/delete, bounded cleanup reconciler; do not return ready when bytes absent. Source `document` ties normalized extracted data to exact file hash/generation/page evidence. Record original is immutable; replacing file creates new record/version, not silently overwriting evidence. Listing pagination50/max100, scoped date/type/status filters, limit filenames/notes; foreign IDs404, stale409, malformed422, unsupported MIME415, too-large413, dependency503 using sanitized error contract.

## Extraction-as-proposal / lab contract

Extraction never creates confirmed Observations by itself. Deterministic file parsing creates bounded text/page regions; Personal AI service, if permitted and actually supports extraction, returns typed candidates through existing adapter. Health validates units/time/schema/evidence and creates Phase 6 pending proposal. No model-provider stack in Health. Extraction is optional disabled by default until external protocol, byte/text retention and privacy policy verified; deterministic parser fixtures/mocked service do not prove actual OCR accuracy. User grants record-specific AI-use permission before outbound text/bytes, separate from cross-domain permission. Minimize pages/content; no generic persistent AI memory copies. If the service cannot extract files, support typed bounded extracted text or pause live feature until contract accepted; do not invent a live endpoint.

Planned `record_extractions` stores owner/record/hash, schema/model/adapter version, bounded candidates, page/region evidence, uncertainty, task status and immutable review revisions. Max200 candidate rows/request; split supported long docs deliberately. Service timeout/size/tool bounds reuse Phase 5 with a documented extraction-specific deadline; long work uses durable SQL task state + bounded worker/Cloud Run Job only when demonstrated needed, no Pub/Sub/event bus. HTTP request interruption must not duplicate candidate sets. Retry keyed `(owner,record_hash,extractor_version,request_id)` and returns known state. Different extraction version creates a new review artifact, not overwritten canonical facts.

Lab v1 Observation payload includes user-reviewed test name, optional verified code/catalog key, typed numeric or text result, original unit if numeric, collection date/time+precision (unknown allowed), report date distinct, optional **as-reported** reference interval/text, specimen notes and record/extraction/page/region evidence. Initial canonical mapped metrics: hemoglobin, HbA1c, LDL cholesterol and creatinine; units validated against the declared metric/version, conversions only if documented dimensionally valid. Other test labels may remain reviewed uncoded lab results with original reported units; they are not silently mapped into trend-comparable clinical metrics. No automatic diagnosis, “normal/abnormal” or treatment interpretation from a reference range. Preserve uncertain OCR text as candidate data until user corrects/explicitly chooses a supported typed result; do not invent units, exact collection midnight or missing values.

Extend Phase 6 typed command registry narrowly with `observation.create` for reviewed lab v1 and necessary record-evidence linkage, or equivalent agreed typed `lab_observation.create`; document exact chosen discriminator before code. Use existing executor/receipt/owner/revision/provenance. Candidate confidence never means user confirmation. User approves selected corrected rows (with deliberate split if max10 commands/proposal), rejects others, and explicit Save applies once. Stable candidate/command IDs plus unique `(owner,extraction,candidate_revision)` receipt mapping prevent repeated imports while allowing explicit new corrected revision. Source remains document/AI-extracted origin with user_confirmed status after review; target history ties record hash/extraction/candidate revision and user edits. Imported Observation edits preserve original and invalidate Phase 7 evidence. Deleting a record alone does not silently delete confirmed results: user chooses remove file only versus file+linked imported data, with evidence-availability indication; full owner deletion removes all.

Mobile Records feature: upload picker/progress/ready/error; list/view with private access; extraction pending/disabled/failure, side-by-side or sequential original/page and candidate rows, uncertain unit/date/mapping fields, select/correct/reject/save and applied results. Accessible reading/forms, retry/draft preservation/session switch. Today/Insights use lab observations only under supported metric methods with explicit units/coverage; context/search adds permitted records **summaries**, never full bytes/signed URLs by default; `health.records` typed read capability respects record and linked evidence permissions.

## Export, deletion and backup contracts

Owner export includes canonical envelopes/subtypes/sources/relationships/revisions/proposals/results/experiments/import metadata and a versioned manifest, stable IDs/units/time/permissions. Optional original record files selected explicitly; no credentials/tokens/signed URLs/internal SQL. Choose JSON as lossless primary format, optional CSV per supported observation catalog with documented flattening; not FHIR. `POST /exports` user-authenticated request plus status/download, owner-scoped task and retention≤24h; small exports may stream, larger use bounded SQL task+local/GCS temporary object. Idempotent request IDs and max limits; snapshot_as_of and DB snapshot keep rows coherent. Manifest records inaccessible/missing file/version, never calls export complete silently when bytes omitted. Clear export copy handling/expiry and local temporary deletion. Requests reauthorize download; no public files.

Deletion is domain-data erasure, not merely archiving. `POST /deletion-requests` requires current user reauthentication/explicit irreversible confirmation, returns owner-bound durable job/status. Pending/running/completed/failed states with idempotent key. Freeze new writes/AI calls/imports/export tasks for that owner on request; revoke domain delegation/temporary links as feasible. Worker executes restartable bounded steps: stop task creation; enumerate private keys; remove records/exports/staging/temp objects with generation checks; erase all owner canonical/subtype/history/source/relationship/proposal/receipt/analytics/experiment/import rows in valid dependency order; verify counts/objects; finish. External deletion failure keeps job incomplete/retryable; don't claim success because DB rows were removed first. No routine logs of deleted health content.

Account identity is shared ecosystem identity: domain deletion does not automatically delete Firebase identity or other apps. Maintain minimum health-free deletion ledger/blocked domain-principal marker required to prevent restore/reimport, with retention tied to backup lifecycle; document retained identifiers/purpose. Renewed app use requires explicit fresh domain principal/consent, never silently restores erased owner. Client clears sensitive caches/HealthKit anchors/account consent and stops sync; native HealthKit originals are outside Health authority and are not deleted. Personal AI external retained context deletion/retention must be coordinated through the real service contract; if it cannot be guaranteed, report precisely which external copies remain and gate any claim of complete ecosystem erasure.

Backup/restore: verify current Neon snapshot/PITR/export capabilities and GCS object/version/retention rules before selecting procedure. Prefer existing managed capabilities plus portable encrypted SQL/object-manifest backups, not new services. Provisional target RPO24h/RTO4h for this personal project, reconcile budget/vendor limits and document actual achieved values. Backup retention30days unless user-approved policy differs; no public/unrestricted downloads or plaintext secrets. Restore into isolated staging, never over live DB as a test; restore DB plus referenced object generations and verify counts/hashes/FKs/history/evidence/units. Replay minimal deletion ledger before serving restored environment so deleted users are not resurrected; suppress access until replay/verification completed. Backup expiry/locked retention may delay physical deletion of backup copies: record exact policy and residual period, don't promise immediate erasure. Preserve ledger beyond oldest backup expiry plus verification margin (provisional31days minimum for30day backup policy), extending for any actual locked/longer backup; client reenrollment cannot reimport without fresh consent. Never reinstate obsolete auth/config secrets from backup.

## Whole-system hardening contracts

Threat/integrity inventory covers owner joins/history/evidence/storage/imports/tools, schema/version/time/unknown invariants, source/confirmation/audit chains, transaction receipts, stale signals and orphan detection. Malformed files/text/tool responses treated as untrusted. Review auth expiration/delegation/secret/log redaction/URL lifetimes/build dependencies. Use synthetic canary health strings to check logs/error telemetry never contain payloads. Record actual dependency findings; fix reachable issues before release or document justified residual risk.

Establish representative synthetic dataset (e.g. 2 owners, 365 days, 10K observations/events per owner, 100 plans/trackers and 50 sample records), seeded outside production. Provisional targets under documented local/staging resources: Today p95≤500ms, filtered lists≤500ms, bounded analytics≤2s excluding external AI, stable pagination and bounded memory during20MB uploads. Measure and reconcile realistic budgets before optimizing; no speculative Redis/time-series/vector store. External extraction/upload network timing reported separately. Validate large font/screen reader/forms/chart alternatives and loss/expiry/conflict UX on actual iOS.

## Work-package order and delivery gates

`P9.1 inventory/privacy/file policy -> P9.2 record lifecycle -> P9.3 extraction review`; `P9.1 -> P9.4 export/deletion/backup`. Both feed `P9.5 security/integrity/performance -> P9.6 release audit`. Privacy/deletion design must precede real document ingestion, not be left to the final review. External file validation/extraction/storage gates control live enablement independently of offline progress.

### P9.1 — Reconcile complete data/retention and file policy

**Dependencies:** Phases 1–8 evidence. **Goal:** exhaustive safety/cleanup map.

**Areas:** existing security/data/deployment/AI docs; provisional record/extraction/lab/task/export/deletion schemas and inventory.

**Work:** enumerate every owner store/object/external copy, real GCS/Neon policies, parse/scan/size bounds, supported lab semantics, extraction protocol/permissions, deletion/backup obligations and performance budgets.

**Requirements:** no hidden external retention or clinical claims. **Tests:** schema/permission/bounds fixtures and completeness checklist against actual migrations. **Acceptance:** safe file/erasure strategy documented before live ingestion. **Out of scope:** provider/FHIR redesign.

### P9.2 — Upload, verify and privately view records

**Dependencies:** P9.1 and actual Phase 3 storage. **Goal:** coherent DB/object lifecycle.

**Areas:** API/application/persistence/integrations/migrations/client, mobile Records/tests; provisional upload intent/record/orphan cleanup.

**Work:** streamed/signed bounded upload, immutable key/generation/hash/finalize/scan state, private download, status/list/view and cleanup/retry.

**Requirements:** no ready state before bytes validated; owner auth; local containment/cloud privacy; no filename path or signed URL logging. **Tests:** MIME mismatch/oversized/encrypted/malicious parse fixture, cross-owner access, expired links, overwrite/finalize race, orphan/interrupted storage/DB failure. **Acceptance:** local + real GCS synthetic round trip and unsafe input cannot become ready. **Out of scope:** automatic extraction or arbitrary public uploads.

### P9.3 — Extract candidates, review and apply lab proposals

**Dependencies:** P9.2, actual Phase 5 adapter and Phase 6 executor. **Goal:** reviewed structured imports with evidence.

**Areas:** integrations/application/domain/API/migrations/client, Records/proposal UI/tests; provisional extraction task/candidate/lab schemas.

**Work:** bounded parser/optional permitted AI extraction, typed candidate/version/page evidence, narrow proposal command extension, review/correct/select/reject and idempotent import, context/search records extension.

**Requirements:** no confirmed values before explicit Save; original unit/precision/provenance retained; partial selected batch explicit. **Tests:** uncertain OCR/unit/date/unmapped metric, duplicate/reordered tasks/partial review/retry/races, foreign file/evidence, expired proposal, failed atomic apply, AI disabled/service malformed/timeout. **Acceptance:** synthetic lab file→review→one canonical result with original/evidence trace; actual extraction accuracy gate separated. **Out of scope:** diagnosis/FHIR/provider APIs.

### P9.4 — Export, erase and recover data safely

**Dependencies:** P9.1 and storage contract; integrate record/import inventory after P9.2/P9.3. **Goal:** user control and proven recovery.

**Areas:** application/persistence/storage/API/mobile settings, infra runbooks/tests; provisional durable task/export/deletion tables and ledger.

**Work:** versioned owner snapshot exports/private temporary downloads, reauthenticated write-frozen deletion with restartable external cleanup, client/cache/HealthKit consent clearing, encrypted backup/object manifest and isolated restore/ledger replay.

**Requirements:** no deleted owner resurrection/reimport, no other-owner/shared-identity deletion, incomplete external deletion reported; bounded worker may use Cloud Run Job only if measured need. **Tests:** snapshot consistency/manifest completeness, two-owner export/erase, crash at each deletion step, external object failures/retry, cache clearing, backup restore with deleted-owner suppression and missing object hashes. **Acceptance:** verified portable export, actual restore drill and domain erasure including histories/receipts/object copies with residual backup/external policy stated. **Out of scope:** deleting platform HealthKit originals or other-app accounts.

### P9.5 — Audit security, integrity and measured performance

**Dependencies:** P9.2–P9.4 integrated. **Goal:** eliminate maturity gaps.

**Areas:** whole API/mobile/infra/contracts/tests/docs; provisional integrity audit command and perf fixtures.

**Work:** owner/tool/storage threat matrix, dependency/container/secret review, canary log test, FK/source/history/receipt/evidence/orphan audits, fixed-dataset profiling and minimal measured fixes, accessibility/session/offline audit.

**Requirements:** source/tests separate, generated contracts authoritative, no speculative infrastructure; remediation stays within delivered product. **Tests:** whole-route owner fuzz/malformed matrix, adversarial files/injection, bounded-query latency/memory, audit on corrupt fixtures plus zero corruption on valid DB. **Acceptance:** critical/reachable security and integrity findings fixed or explicitly block release; budgets evidence recorded. **Out of scope:** new roadmap products to improve demo appearance.

### P9.6 — Validate release and reconcile completed roadmap

**Dependencies:** all packages, real external gates. **Goal:** evidence-backed mobile/backend maturity.

**Areas:** E2E tests/runbooks/architecture/model/roadmap docs; provisional phase-9 release evidence.

**Work:** clean local/staging bootstrap and full synthetic Profile→Add→Plan→Assistant→proposal→Insights→HealthKit→Record→export/erase scenario; provider/device checks separately; update actual architecture/contracts and deferred-web readiness gaps only.

**Requirements:** mocks never certify cloud/Apple/extraction; record external residuals, no automatic future-web launch. **Tests:** migrations and rollback, generated-client drift, E2E/recovery/data integrity/log/privacy/performance/accessibility; actual documented device/cloud/provider matrix. **Acceptance:** completion criteria below met with evidence, no hidden unfinished safety gates. **Out of scope:** detailed web phase plans/implementation.

## Migration/rollback and verification matrix

Additive records/extractions/lab/task schemas with explicit schema versions; old manual/device Observations keep original semantics. Applied proposal history/receipts remain readable; lab command extension cannot bypass confirmation. Record storage migrations must maintain object key/generation references; backfill validated states rather than assuming every object exists. Deployment rollback disables new uploads/extraction but does not erase record files/results/tasks. Deletion once running is irreversible and cannot be “rolled back” from a stale backup; backup restores must replay ledger. Runtime image downgrade only if schema compatible; otherwise roll forward or restore isolated verified data under runbook.

| Risk                    | Deterministic offline/local evidence                                 | Actual required gate                                              |
| ----------------------- | -------------------------------------------------------------------- | ----------------------------------------------------------------- |
| File/object lifecycle   | Signature/MIME/parser bounds, races/orphans/path tests               | GCS private upload/finalize/signing/scan policies                 |
| Extraction/confirmation | Fixed synthetic lab candidates, uncertain fields, receipt replay     | Real extractor/OCR auth/accuracy/retention and reviewed samples   |
| Export/erasure          | Two-owner manifests, crash recovery, every table/store inventory     | Real object deletion and external/backup retention verification   |
| Backup/recovery         | Synthetic restore integrity/ledger fixtures                          | Isolated Neon + object generation restore drill, measured RPO/RTO |
| Security/integrity      | Auth/tool fuzz, canary logs, corrupt/valid audits, dependency review | Deployed TLS/IAM/logs and actual enabled Apple/provider checks    |
| UX/performance          | Component/E2E/fixed dataset/query/memory checks                      | iOS accessibility/file review and staging latency                 |

## Phase acceptance and completion review

Accept when private records upload/view safely; lab extraction remains a proposal until review and applies once with evidence; export and domain deletion cover every owner store; backups actually restore without resurrecting erased users; complete product tests/security/integrity/performance checks pass. Manual/local/AI-disabled/non-HealthKit behavior still usable. No deferred integrations or web work.

Before declaring Phase 0–9 mature: Is every health value traceable to source/revision/evidence? Can user export/erase data and understand external/backup limits? Are file/parser/tool boundaries secure? Has recovery been performed rather than described? Are enabled integrations verified on real systems? Are all material security findings fixed and remaining external gates explicit? Does the final native/shared/backend architecture preserve future web without premature abstraction?

The implementing session must create planned `docs/implementation/evidence/phase-9-release.md`: actual migrations/head/record/lab/extraction/export/deletion routes/states/limits, object/privacy/extraction permission/retention policy, proposal extension and generated commands, cleanup inventory and backup/restore/ledger runbook/results, complete offline vs cloud/device/provider matrix, performance dataset/resources/measurements, security/integrity findings and remediation, residual decisions and final roadmap reconciliation. Record external unverified capabilities as disabled/unfinished; do not manufacture release sign-off or post-implementation guides during planning.
