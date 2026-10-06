# Personal AI integration

Personal AI is the shared intelligence layer; Health is the domain authority.

Personal AI owns LLM routing, general conversation/memory, web/research orchestration, cross-domain reasoning, and shared agent/tool orchestration. Health owns canonical state, schema/validation, domain retrieval/analytics, context construction, and action persistence.

The Health service builds task-specific `HealthContextPack`s instead of dumping the full profile. Candidate sections: request context, constraints, active contexts, goals, preferences, today, recent summaries, relevant events/observations/trends/records, provenance.

Read capabilities conceptually include context, search, today, profile, goals, plans, trends, records. Mutations are proposals for events, profile changes, goals, plans, and trackers.

Health facts discovered in conversation should be proposed into Health rather than stored as competing generic durable memory. Cross-app sharing is explicit.

Design for general wellness, education, personally consequential medical reasoning, and urgent-safety classifications with progressively stricter grounding/action policies.

## Phase 5 implementation boundary

Health currently implements versioned `HealthContextPack` v1 preview and
AI-permission-filtered full-text search. The pack contains only active,
temporally eligible owner objects that the user individually marked
`ai_use_allowed` and selected by resource type. Daily summaries cover only the
included, opted-in entries, and evidence references identify exact object
revisions. Text and notes remain untrusted data. Cross-domain permission is a
separate flag and does not authorize this Assistant.

The mobile Assistant shows the requested scope and local preview. The provider
adapter remains disabled: this repository has no Personal AI service or
supplied endpoint, service identity, delegation, tool callback, or retention
contract. `PERSONAL_AI_ENABLED=true` is rejected and no destination URL is
configurable. Message submission therefore fails closed with a sanitized 503;
context preview and permission-filtered search continue to work locally. Do
not claim live service compatibility or safety evaluation from this state.

When the service contract is supplied, Health must keep ownership and
per-object permission checks at every read, bind delegation to a short-lived
owner/request scope, rebuild context at send time, and validate every cited
revision. The Phase 5 launch gate remains the real service auth, retention,
timeout, tool registration, safety-copy and live read-only evaluation.
