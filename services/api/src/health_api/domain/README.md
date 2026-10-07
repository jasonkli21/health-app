# Domain layer

`schemas.py` is the versioned registry for Profile v1 and, since Phase 2, the
type-specific JSONB payloads for daily Event and Observation v1 contracts. Event
and Observation DTOs combine those payloads with relational time, metric, unit
and common-envelope notes. Keep kind/category compatibility,
unknown-versus-false/zero behavior, supported units, strict time precision, and
half-open UTC validity rules here. New types and payload versions are added only
with their owning roadmap phase; never reuse a registered version for a changed
shape.

`daily.py` defines the immutable `unit-v1` conversion factors and maps each
metric to its canonical display/summary unit. `daily_rollups.py` owns the fixed
`today-v1` methods; it does not infer nutrients or activity and keeps absent
measurements sparse. Date-only inputs retain only their entered local date and
IANA zone. They are assigned to that calendar date for Today and are never
converted to a fabricated midnight sample. Exact intervals use half-open UTC
day bounds and elapsed overlap; a workout's distance is attributed to its start
day because no route samples exist to distribute it across days.

Daily numeric inputs have a software bound of `1e300` for both the entered
quantity and its canonical conversion. Unit-aware validation rejects a duration
or distance that would cross that bound before persistence; this is a numeric
safety rule, not a clinical limit. Today caps a snapshot at 10,000 candidate
objects; the canonical bound and candidate cap keep valid subtotals below the
IEEE-754 maximum, while checked `fsum` rejects non-finite results. Sleep may be
logged with only a date or an exact start;
without an end, duration remains unknown and coverage stays partial. Symptom
severity coverage uses active, same-day symptom episodes and their active linked
Observations only; unrated episodes stay in the denominator.

`proposals.py` defines the closed Phase 6 command union and its size, command
count, evidence, revision, expiry, and confirmation bounds. Proposal commands
reuse the existing Profile, Event/Observation, goal, plan, and tracker schemas;
they are never generic JSON patches. Permission changes and destructive
commands are outside this registry.

`analytics.py` freezes the Phase 7 metric catalog, derived result schemas, and
method versions. `trend-v1/unit-v1` reuses `summarize_today` and its `unit-v1`
conversions, retains nulls for missing days, labels rolling means over seven
known samples, and compares calendar-window halves only with five known days in
each. `spearman-sameday-v1` uses average ranks for ties and same-day lag 0 for
five predefined pairs; it requires 14 paired days over at least 21 calendar
days and reports constant/insufficient data without a statistic. Numerical
tracker analysis is limited to number/quantity fields and an exact immutable
schema version. These are descriptive software methods, not clinical
thresholds or causal estimates.

`healthkit_imports.py` defines the closed normalized batch, tombstone,
receipt, status, and aggregate source-preference contracts. `StepCountValueV1`
and the resting-heart-rate/heart-rate-summary Observation metrics are additive
Phase 8 values. Sleep stage, source labels, and bounded aggregate method/count/
range/coverage fields are allowlisted metadata; native HealthKit objects and
raw high-frequency arrays are not accepted.
