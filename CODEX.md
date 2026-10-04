# Codex repository instructions

Start by reading `docs/handoff/codex-handoff.md` and the documents it references.

## Scope rule

The repository is a bootstrap scaffold. Verify and improve the scaffold, documentation consistency, developer ergonomics, and Phase 0 foundation only unless explicitly instructed to implement later phases. Detailed planning for later phases is allowed when the handoff prompt explicitly requests it.

Do **not** silently start Phase 1+ product work. Authoring Phase 1–9 implementation-plan documents is not permission to implement those phases. Do **not** start the future web implementation unless explicitly instructed after the initial Phase 0–9 roadmap is complete.

## Engineering rules

- Keep source and tests in separate directories.
- Keep FastAPI route handlers thin; domain/application logic belongs below the API layer.
- Health canonical state belongs to this domain service, not the Personal AI System.
- The Personal AI System must not receive direct database credentials.
- AI-originated state changes use typed proposals and explicit user confirmation unless the user is already in an explicit save flow.
- Preserve provenance, temporal validity, and unknown-vs-zero semantics from the start.
- Use relational structure for queryable concepts and validated JSONB only for extensible type-specific payloads.
- Avoid speculative infrastructure: no Redis, Pub/Sub, external vector DB, time-series DB, or event bus without demonstrated need.
- Prefer simple, human-readable modules and comments that explain non-obvious intent rather than restating code.
- Maintain local and cloud portability; ordinary development must not require cloud resources.
- Treat health data as sensitive. Never put health payloads in routine logs.
- Preserve a clean future web path: native-only integrations such as HealthKit must remain behind mobile-specific adapters; shared frontend packages must not transitively import native modules.
- Optimize future mobile/web sharing around contracts, frontend-safe domain utilities, and design tokens—not forced component reuse.

## Verification before substantive implementation

Before implementing a phase, reconcile the phase plan against the current repository, document gaps or inconsistencies, and state any proposed deviations explicitly.
