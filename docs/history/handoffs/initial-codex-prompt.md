> Historical one-time prompt for the scaffold review and plan authoring. It is
> not current guidance or implementation authorization. See AGENTS.md and
> docs/current-state.md.

# Initial Codex prompt

Use **Sol High** for this session.

Review this repository as a newly generated Personal Health scaffold. Read `CODEX.md` and `docs/handoff/codex-handoff.md`, then reconcile the full repo against the documented product, UX, architecture, data model, security model, AI boundary, and Phase 0 requirements.

Be thorough: check structure, source/test separation, manifests, commands, local setup, dependency/version compatibility, contracts, documentation consistency, security footguns, unnecessary complexity, and missing Phase 0 pieces. Run available scaffold checks and lightweight validation.

You may make small fixes necessary to make **Phase 0** coherent and runnable, but **stop before implementing Phase 1 or any substantive product functionality**. Do not add health tables/domain logic, product screens, AI behavior, HealthKit, cloud deployment, or the future web app.

Treat the future-web architecture and `web-extension-plan.md` as deferred constraints only: preserve clean shared-package and native-adapter boundaries, but do not prematurely refactor or abstract mobile code for hypothetical reuse.

After the Phase 0 review/fixes are complete and the scaffold is internally consistent, perform a second documentation-only task: create detailed implementation plans for **Phases 1–9** of `docs/implementation/implementation-plan.md` using `docs/handoff/phase-plan-authoring-standard.md` as the planning contract.

These phase plans will be handed to a **Luna Max** agent for implementation later. Make them repository-grounded, self-contained, precise enough to execute without redesigning the phase, and explicit about dependencies, scope boundaries, invariants, data/API/UI contracts, work-package order, failure cases, tests, acceptance criteria, and implementation handoff evidence. For later phases, do not pretend future paths/contracts already exist: mark planned artifacts as provisional and require implementation-time reconciliation against the completed preceding phases.

Create:

```text
docs/implementation/phases/README.md
docs/implementation/phases/phase-1-implementation-plan.md
...
docs/implementation/phases/phase-9-implementation-plan.md
```

Do not implement any Phase 1–9 code while authoring these plans, and do not create detailed web-extension phase files yet. Do not blindly apply a template: vary the plan structure and depth where the phase warrants it while satisfying the planning standard.

Finally, review all nine plans together for cross-phase consistency and report:

- what you reviewed in the scaffold;
- Phase 0 issues found and fixes applied;
- commands/tests run and results;
- architecture/roadmap changes made or still requiring user review;
- the phase-plan files created;
- any unresolved decisions or external verification gates called out in those plans;
- whether the repository is ready for a Luna Max implementation of Phase 1.
