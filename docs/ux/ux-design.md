# UX architecture

## Navigation

Five primary areas: Today, Plan, Assistant, Insights, Profile. Health domains such as nutrition, exercise, and sleep are modules within these surfaces.

## Today

A configurable combination of at-a-glance modules, today's plan/regimen items, a timeline, relevant insight/recommendation cards, and universal `+ Add`. Empty states must say not logged/unknown rather than fake zeros.

Today keeps scheduled intent beside the health timeline. A scheduled item begins
as unknown; the user can mark it complete, skip it, or move it to an offset-aware
new time. A completed plan occurrence does not create an Event or Observation.
Context cards show temporary relevance and explicit priority without replacing
Profile or changing regimen state. Schedule DST resolution is shown when the
local slot was adjusted.

## Plan

Plan groups goals, regimens, plans, contexts, and custom trackers. Goal forms
support a declared metric target and time window but show progress as not
estimated. Regimen forms accept only the user's own quantity and instructions;
the app does not suggest doses or interactions. Plans have ordered stable items
and explicit dates. Users may create or edit daily/weekly regimen and plan-item
schedules with a local time, IANA timezone, recurrence interval, and
future-effective date. Schedule changes preserve earlier occurrence history.

Contexts carry a validity window, priority, notes, and optional explicit links
to Profile items, goals, or regimens. They are relevance metadata and never
silently alter canonical profile facts or pause treatment.

## Profile

An editable health knowledge base organized into categories rather than one giant form.

## Universal Add

Supports structured quick actions and natural-language capture that becomes a preview/proposal.

## Custom trackers

Users can define structured trackers with bounded text, number, boolean, enum,
date, and unit-bearing quantity fields. Field IDs remain stable within a schema
version; edits create a new version so older entries remain interpretable.
Optional missing fields stay absent while `false` and `0` remain explicit
values. Universal Add and Plan both provide a custom tracker entry form. An
archived tracker remains available to read its historical entries, and does not
accept new ones. AI-generated schema proposals are deferred to a later phase
and will require user confirmation.

## Assistant

Shows context scope and converts useful conversation outcomes into optional actions. General chat never silently mutates canonical state.

## Insights

Separate trends, patterns, insights, and experiments. Preserve evidence and uncertainty.

## Future web UX

The web client should not copy mobile screens literally. It should specialize in large-screen analytics, record review, profile/plan editing, experiments, and long-form Assistant/research workflows while preserving the same domain semantics. See `docs/web/web-extension-architecture.md`.
