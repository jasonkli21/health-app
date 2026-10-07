# Phase 7 local implementation evidence

**Checkpoint:** October 7, 2026. Deterministic analytics, evidence-linked
insights/recommendations, manual experiments, generated API contracts, and the
mobile Insights/Today surfaces are implemented in the local source tree. This
record distinguishes source/static verification from database, device, and
provider acceptance.

## Scope and method contract

Health remains the only canonical health store. `derived_signal`, `insight`,
`recommendation`, and `experiment` records use the existing owner envelope and
revision history. `analytics_artifacts` stores versioned payload/state, and
`analytics_evidence` has owner-scoped foreign keys to exact source revisions.
No separate analytics database, queue, cache, or background recomputation was
introduced.

The supported daily metrics are known meal-energy subtotal, exercise duration
and distance, sleep duration, symptom severity and episode count, weight,
temperature, systolic/diastolic pressure, and pulse. The result catalog
describes each unit and aggregation. Numeric/quantity custom tracker fields
use `tracker:<tracker-uuid>:<field-id>:v<schema-version>` and retain one
immutable field schema version; boolean, enum, text, and date fields are not
analyzed.

`trend-v1/unit-v1` delegates unit conversion, interval overlap, date-only
assignment, and daily aggregation to Phase 2 `summarize_today`. It emits every
calendar date, leaves unknown days null, reports logged/known/total/partial
coverage, computes `fsum` mean and median, and labels rolling means over seven
known samples. It compares the two calendar-window halves only when each has
five known days; a zero baseline has no percent change. The API returns the full
bounded window and the mobile table displays the most recent 14 dates while
retaining full-window coverage.

`spearman-sameday-v1` uses deterministic average ranks for ties and five fixed
lag-0 pairs: sleep duration/symptom severity, exercise duration/sleep duration,
exercise duration/symptom episode count, energy/symptom severity, and sleep
duration/pulse. It requires 14 paired values across 21 calendar days, returns
explicit insufficient/constant states, and does not report significance or
causation.

Each analysis request is bounded to 366 inclusive local dates and 10,000 total
active Event/Observation inputs. Multi-metric refreshes share one source load;
PostgreSQL queries use a transaction-local two-second statement timeout.
Derived signal IDs are deterministic over owner, scope, and input fingerprint.
Evidence references carry exact owner object/revision/type. Daily updates and
archives stale only dependent artifacts in the same transaction; a new daily
write conservatively stales current analytics so the next on-demand compute
sees it. Phase 8 imports must call the same invalidation hook in their owner
transaction.

## Insights, recommendations, and experiments

Insights use deterministic templates and require their catalog comparison or
association threshold to pass. Insight/recommendation expiry defaults to seven
days and is bounded to 30 days. Expiry is applied on reads/actions. The only v1
recommendation is to continue logging when a window has sparse coverage. It is
not a structured Health action: acceptance records interest only and creates
no Health write or Phase 6 action proposal. Dismissal/acceptance uses expected
artifact revisions.

Experiments are user-authored drafts with one primary outcome metric, ordered
baseline/intervention dates, optional exact planning-resource revision, and
manual lifecycle transitions. Starting requires an active metric/resource and
at least one known baseline outcome in the owner's local timezone; the daily
generation is checked again before the start commits. Outcome design fields
cannot change after start, while notes can. Results report selected timezone,
mean/median, known/missing days, and current exact source revisions as a
descriptive comparison. They do not infer causality.

The optional AI context extension requires an explicitly selected trend metric,
both daily resource types, and no domain filter. It recomputes only from active
AI-permitted inputs at context construction. Numeric tracker summaries also
require an active AI-permitted tracker definition. Personal AI remains disabled;
no provider call or AI-generated insight was added.

## API, persistence, and generated client

Migration `f7c8d9e0a1b2` follows `20261006b1a2` and is the single Alembic head.
It extends the allowed analytics envelope types and creates
`analytics_artifacts` and `analytics_evidence`. Downgrade refuses to discard
Phase 7 history. The OpenAPI contract exposes 17 owner-scoped analytics routes
for catalogs, trends, associations, insight refresh/history/actions,
recommendation history/actions, and experiment CRUD/lifecycle/results. List
cursors bind to owner and filters; update/actions require expected revisions.
Unknown/foreign objects remain 404; stale writes use 409; invalid ranges,
metrics, pairs, or experiment state use 422.

OpenAPI is exported with
`services/api/scripts/export_openapi.py`; the generated client is emitted by
`packages/api-client/scripts/generate-client.mjs`. The checked-in
`contracts/openapi/openapi.json` and `packages/api-client/src/generated.ts`
were regenerated from FastAPI.

## Local verification recorded

- API import and OpenAPI generation succeeded: 63 paths and 194 schema
  components.
- Python source and migration `compileall` succeeded.
- Ruff checks passed for the changed API/domain/application/persistence and
  migration source.
- Mypy passed for all 38 API source files.
- Alembic reports `f7c8d9e0a1b2 (head)`; offline `alembic upgrade head --sql`
  generated SQL through the new artifact/evidence tables.
- Mobile TypeScript `tsc --noEmit` and ESLint passed for Insights, Today, and
  route files.
- OpenAPI/client generation and `git diff --check` are part of the final local
  check record for this commit.

Automated numerical fixtures, API/mobile test suites, and PostgreSQL-backed
migration lifecycle, schema drift, ownership/concurrency, and query-plan checks
were not run. Offline SQL generation does not demonstrate a live migration or
database behavior. Mobile device accessibility/timezone/session review and
actual provider/safety review remain open. No clinical validity or efficacy is
claimed.
