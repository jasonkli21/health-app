# Current implementation state — Health

Updated 2026-10-14. This is the living delivery boundary. Code, contracts,
migrations and tests take precedence over plans. The stabilization patch is based
on `7fb84c76217c772b2bce6715744b8294afafa771`; final commit/source identity and exact checks are recorded in the
[verification record](stabilization-2026-10-14.md). Independent final review and
external acceptance remain open.

## Implemented locally

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
The mobile task card now chooses a linked user's active Shopping project via
the generated API client instead of asking for a UUID and revision. SecureStore
recovery separates create, submit, validation, confirmation and effect-unknown
phases, preserves the original IDs, and clears stored task state when the
authenticated owner changes. `migrations/historical-sha256.txt` freezes each
existing migration's bytes; Ruff formatting excludes those exact files while
keeping new migrations under normal formatting rules. API/native/static/mobile checks and JS bundle evidence are recorded separately
from HealthKit device, cloud IAM/storage, Terraform provider and recovery gates.

## Verification and release boundary

Read [the local stabilization evidence](stabilization-2026-10-14.md) and
[suite verification](https://github.com/jasonkli21/personal-ai-agent/blob/main/stabilization/VERIFICATION.md).
The all-five synthetic PostgreSQL/loopback HTTPS paths do not prove real IAM,
provider, cloud, browser or native-device behavior. Feature gates remain off by
default. No cloud deployment or live-provider operation was run. The user
authorized local commits followed by pushes to each remote `main`. Hosted CI is
separate evidence.

## Minimum context

Read [the router](README.md), the owning module/contract and focused tests.
[Suite contracts](https://github.com/jasonkli21/personal-ai-agent/blob/main/stabilization/CROSS-REPO-CONTRACTS.md),
[operations](https://github.com/jasonkli21/personal-ai-agent/blob/main/stabilization/OPERATIONS.md) and the
[fresh re-review handoff](https://github.com/jasonkli21/personal-ai-agent/blob/main/stabilization/FRESH-REVIEW-HANDOFF.md) explain
cross-app assumptions and remaining acceptance. The
[previous status](history/stabilization/current-state-before-2026-10-14.md)
preserves detailed predecessor phase evidence and unresolved gates. This status
does not authorize implementation of the future roadmap.
