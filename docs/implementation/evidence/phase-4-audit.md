# Independent audit of Phase 4 correction commit `80a8c96`

Audit date: October 5, 2026. Reviewed the correction diff against the original
independent review, implementation plan, ORM constraints, occurrence/Today
integration, generated contract, and mobile request/draft lifecycle.

## Additional gaps corrected

- Retiring a scheduled manual task violated the link target CHECK. Added migration
  `b8a125fec731`, retaining NULL targets for retired tasks. Repeated reorder/update
  now uses temporary positions disjoint from both live and retired rows. Retired
  items cannot acquire a new schedule.
- Recorded occurrences could no longer be acted on after effective schedule
  edits. Actions now use the recorded immutable schedule revision; legacy timing
  provenance is backfilled. Omitted association fields preserve existing links,
  including archived historical associations; explicit null clears them.
- Today parent discovery hid recorded occurrences after archive, pause, or item
  retirement. Recorded history remains visible with explicit `can_act`; generated
  intent uses the schedule timezone for resource validity. Queries bound override
  reads and avoid repeated link reads/parsing; Today sorts across parents.
- Editor refetches silently advanced stale drafts onto changed server revisions.
  Content/permission conflicts now require an explicit reload that replaces the
  draft. Schedule editors follow the same rule; schedule-only parent revisions
  may advance without discarding content drafts.
- Picker, overview, and tracker pagination could accept stale results. Request
  scopes guard them; tracker refocus discovers newly created definitions while
  retaining the schema of an existing draft. Initial picker failures are visible.
- Late account/day responses could navigate or alter recovery state. Profile
  creation, rescheduling, overview lifecycle actions, and Today actions now guard
  completion against session/request changes. Today shows the due instant after
  completing a moved occurrence and refuses unavailable association selections.

## Verification

- API: **113 passed, 46 skipped** (`pytest services/api/tests -q`). New tests
  exercise real link writes and constraints in a small portable fixture,
  repeated retirement/reorder, immutable recorded actions, association
  preservation, recurrence/DST, and three PostgreSQL integration scenarios.
- Mobile: **94 passed across 20 files**. Added draft revision tests and deferred
  account-A success/failure tests against the actual Profile create screen.
- Python typing, changed-file Ruff lint/format, mobile TypeScript and ESLint,
  generated OpenAPI/client, changed mobile/client formatting, and whitespace
  checks passed. Offline Alembic upgrade SQL reaches the single head
  `b8a125fec731`.

## Remaining acceptance gates

No live PostgreSQL database was supplied. A disposable cluster initialization
attempt failed due to host SysV shared-memory exhaustion, even with mmap/posix
settings. The 46 skipped database tests include the three new integration tests.
Portable constraints and offline SQL do not establish PostgreSQL migration
cycle/drift, transactional concurrency, or query-plan acceptance. Run the full
suite against a disposable `TEST_DATABASE_URL`, including migration
upgrade/downgrade/re-upgrade and `alembic check`, before closing that gate.
Cloud parity and simulator/device accessibility, timezone presentation, and
end-to-end acceptance also remain open as documented in the release evidence.
No additional confirmed source defects remain from this audit; these are
unverified environment-dependent gates, not passing acceptance claims.
