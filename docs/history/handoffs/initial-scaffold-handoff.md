> Historical scaffold handoff. Its Phase 0-only restriction and read order are
> superseded. Current repository instructions are in AGENTS.md; start with
> docs/README.md and docs/current-state.md.

# Initial scaffold handoff

## Objective

This repository is the initial scaffold for the Personal Health application. Your first task is to **review and verify the scaffold**, not implement product phases. After that review is complete, the initial Sol High handoff also asks for documentation-only detailed Phase 1–9 implementation plans intended for later Luna Max execution.

## Read order

1. `README.md`
2. `docs/project-brief.md`
3. `docs/ux/ux-design.md`
4. `docs/architecture/architecture.md`
5. `docs/data/data-model.md`
6. `docs/ai/personal-ai-integration.md`
7. `docs/security/security-privacy.md`
8. `docs/deployment/technology-deployment.md`
9. `docs/implementation/implementation-plan.md`
10. ADRs under `docs/architecture/adr/`
11. `docs/handoff/phase-plan-authoring-standard.md`
12. `docs/web/web-extension-architecture.md` and `docs/implementation/web-extension-plan.md` as deferred multi-client context only

## Initial Codex task

Perform a repo-wide scaffold review. Reconcile docs, structure, manifests, local setup, API/mobile shells, and implementation plan. Identify contradictions, missing Phase 0 pieces, awkward directories, broken commands, dependency/version incompatibilities, security footguns, or unnecessary complexity.

You may implement **only small Phase 0 fixes** needed to make the scaffold coherent and verifiable. Do not start Phase 1, database product tables, product UI, AI integration, HealthKit, cloud deployment, or the future web app.

The separate web documents are architectural constraints for future extensibility, not current implementation scope. Preserve mobile-specific native isolation and shared-package boundaries without prematurely abstracting mobile code.

After the Phase 0 review/fixes, follow `docs/handoff/phase-plan-authoring-standard.md` to author detailed Phase 1–9 plan files under `docs/implementation/phases/`. This is documentation-only work for later Luna Max implementation; do not implement those phases. Then report what you reviewed, Phase 0 issues/fixes, commands/tests, design changes requiring review, generated phase-plan files, unresolved decision/verification gates, and whether the repo is ready for Phase 1 implementation.

## Core decisions

Mobile-first Expo/RN; FastAPI; Postgres/Neon; Cloud Run/GCS; Health owns state; Personal AI owns model/research/conversation; typed domain APIs only; relational + validated JSONB; provenance/time from Phase 1; unknown != zero; selective HealthKit persistence; AI mutations use confirmation proposals; no speculative infrastructure; future web is a separate post-Phase-9 Next.js client over the same backend.
