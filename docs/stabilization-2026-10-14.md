# Health stabilization evidence — 2026-10-14

Base revision: `7fb84c76217c772b2bce6715744b8294afafa771`. This record covers the committed stabilization patch,
including earlier Luna changes reconciled by direct implementation QA. Independent
final review is intentionally owned by a separate session.

Health owns profile/history, daily observations, planning, analytics, typed
proposals, consent, revisions, HealthKit receipts and owner export/erasure. Broad
Health context read still requires a Firebase user token and stays unavailable
to PAI's Google path. The independently gated narrow federation route now mounts
without requiring the broader read flag. Sensitive document ingress stays closed.

The separate default-off Shopping path sends only explicitly consented ergonomic
context. Current Firebase authentication resolves the configured Google provider
link to the existing active owner; revocation/disabled membership are rechecked.
The canonical signed verifier replaces duplicate JWT logic. Migration20261014c1d2
adds source commands to active-owner fencing and export/erasure inventories, and
refuses populated rollback. The mobile card uses the generated API client and
keeps original command/confirmation identity during uncertain recovery.

The local restore primitive replays current completed/requested erasure markers
into an isolated restore and keeps pending private cleanup unaccepted. It does
not promote a cloud restore. Baseline readiness preserves the SQLAlchemy URL
object (including its password); owner creation flushes before provider binding.
Timezone/domain and unordered membership assertions preserve their intended rules.
API/native/static/mobile checks and JS bundle evidence are recorded separately
from HealthKit device, cloud IAM/storage, Terraform provider and recovery gates.

Body deadlines use the event-loop clock, independently of log timing. A
distinct-epoch regression and the final all-five HTTPS matrix cover the uvloop
case. Explicit Ruff first-party ownership and generated-format globs make the
actual root CI invocation consistent with API-local checks.

Fresh UTC CI exposed one date-only meal fixture relying on the machine
timezone. The fixture now explicitly chooses America/Los_Angeles; the production
default remains the device timezone. The full mobile suite is rerun under UTC
and America/Los_Angeles.

## Evidence authority

[Exact commands/counts/source identity](https://github.com/jasonkli21/personal-ai-agent/blob/main/stabilization/VERIFICATION.md),
[transition verification](https://github.com/jasonkli21/personal-ai-agent/blob/main/stabilization/LUNA-TRANSITION-VERIFICATION.md)
and [review priorities](https://github.com/jasonkli21/personal-ai-agent/blob/main/stabilization/REVIEW-HANDOFF.md)
are the suite evidence index. Earlier records retain their original date/results;
newer local evidence supersedes their unrun-local-check statements only.

No personal records were used or deleted. Local tests created disposable databases
and synthetic private-store directories. Root-owned test processes are stopped at
handoff. Credentials, private payloads and unrelated user files are excluded from
commits. Cloud/provider/device/hosted CI acceptance cannot be inferred from this
local patch, and erasure does not independently invalidate previously downloaded
exports or historical cloud backups.
