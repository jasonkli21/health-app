# UX architecture

## Navigation

Five primary areas: Today, Plan, Assistant, Insights, Profile. Health domains such as nutrition, exercise, and sleep are modules within these surfaces.

## Today

A configurable combination of at-a-glance modules, today's plan/regimen items, a timeline, relevant insight/recommendation cards, and universal `+ Add`. Empty states must say not logged/unknown rather than fake zeros.

## Profile

An editable health knowledge base organized into categories rather than one giant form.

## Universal Add

Supports structured quick actions and natural-language capture that becomes a preview/proposal.

## Custom trackers

Users can define structured trackers with primitive field types; AI may propose schemas but users confirm.

## Assistant

Shows context scope and converts useful conversation outcomes into optional actions. General chat never silently mutates canonical state.

## Insights

Separate trends, patterns, insights, and experiments. Preserve evidence and uncertainty.

## Future web UX

The web client should not copy mobile screens literally. It should specialize in large-screen analytics, record review, profile/plan editing, experiments, and long-form Assistant/research workflows while preserving the same domain semantics. See `docs/web/web-extension-architecture.md`.
