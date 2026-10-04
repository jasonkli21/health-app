# Personal AI integration

Personal AI is the shared intelligence layer; Health is the domain authority.

Personal AI owns LLM routing, general conversation/memory, web/research orchestration, cross-domain reasoning, and shared agent/tool orchestration. Health owns canonical state, schema/validation, domain retrieval/analytics, context construction, and action persistence.

The Health service builds task-specific `HealthContextPack`s instead of dumping the full profile. Candidate sections: request context, constraints, active contexts, goals, preferences, today, recent summaries, relevant events/observations/trends/records, provenance.

Read capabilities conceptually include context, search, today, profile, goals, plans, trends, records. Mutations are proposals for events, profile changes, goals, plans, and trackers.

Health facts discovered in conversation should be proposed into Health rather than stored as competing generic durable memory. Cross-app sharing is explicit.

Design for general wellness, education, personally consequential medical reasoning, and urgent-safety classifications with progressively stricter grounding/action policies.
