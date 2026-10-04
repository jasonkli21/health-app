# API contract direction

Planned resource groups include `/profile`, `/events`, `/observations`, `/regimens`, `/contexts`, `/goals`, `/plans`, `/trackers`, `/experiments`, `/insights`, `/recommendations`, `/records`.

AI/domain routes should remain narrow and domain-oriented rather than exposing generic database access.

A user explicitly saving through a structured UI is confirmation. Assistant-derived changes create proposals.

Pydantic/FastAPI generates OpenAPI; both mobile and future web clients consume generated TypeScript clients rather than maintaining duplicate handwritten request/response types.
