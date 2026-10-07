# Personal AI integration

Personal AI is the shared intelligence layer; Health is the domain authority.

Personal AI owns LLM routing, general conversation/memory, web/research orchestration, cross-domain reasoning, and shared agent/tool orchestration. Health owns canonical state, schema/validation, domain retrieval/analytics, context construction, and action persistence.

The Health service builds task-specific `HealthContextPack`s instead of dumping the full profile. Candidate sections: request context, constraints, active contexts, goals, preferences, today, recent summaries, relevant events/observations/trends/records, provenance.

Read capabilities conceptually include context, search, today, profile, goals, plans, trends, records. Mutations are proposals for events, profile changes, goals, plans, and trackers.

Health facts discovered in conversation should be proposed into Health rather than stored as competing generic durable memory. Cross-app sharing is explicit.

Design for general wellness, education, personally consequential medical reasoning, and urgent-safety classifications with progressively stricter grounding/action policies.

## Authorization and data flow

Health may build a versioned, minimized context preview from canonical
owner-scoped resources. Every included object must be active and temporally
eligible, and the owner must have explicitly enabled its AI-use permission.
Task scope and per-request exclusions can narrow that set but cannot grant
permission. Context size, included resources, and evidence are bounded and
revision-linked. User text and notes remain untrusted data; relationship
metadata must not make an unauthorized endpoint searchable or visible.

Cross-domain permission is separate and does not authorize this Assistant.
Health rebuilds context immediately before any future provider send, checks
permissions again on every read, binds delegation to a short-lived
owner/request scope, and validates every cited revision. If any required
provider identity, delegation, callback, retention, timeout, or safety contract
is absent or unreviewed, provider messaging and AI-originated proposal
submission must remain disabled. Health-side preview/search and owner-authored
structured proposals are separate local capabilities.

See [current state](../current-state.md) for what is implemented and
[Phase 5 evidence](../implementation/evidence/phase-5-release.md) for the
verified preview/search boundary and open provider gates.
