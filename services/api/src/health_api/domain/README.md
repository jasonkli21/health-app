# Domain layer

`schemas.py` is the Phase 1 versioned registry and Profile v1 contract. Keep
kind/category compatibility, unknown versus false/zero, supported units, and
half-open UTC validity rules here. New types and payload versions are added only
with their owning roadmap phase; never reuse a registered version for a changed
shape.
