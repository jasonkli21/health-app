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
