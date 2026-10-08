import { describe, expect, it } from "vitest";

import type { PlanningEditorDraft } from "../src/features/planning/draft";
import { buildPlanningMutation } from "../src/features/planning/draft";

function draft(
  overrides: Partial<PlanningEditorDraft> = {},
): PlanningEditorDraft {
  return {
    kind: "goal",
    id: "item-1",
    original: null,
    label: "Move more",
    domain: "exercise",
    category: "habit",
    startDate: "",
    endDate: "",
    targetDate: "",
    targetMetric: "none",
    targetComparator: "at_least",
    targetValue: "",
    targetUnit: "min",
    targetPeriod: "once",
    regimenQuantity: "",
    regimenUnit: "dose",
    regimenInstructions: "",
    contextNotes: "",
    contextPriority: "0",
    contextRelated: [],
    fields: [{ id: "value", label: "Value", kind: "text", required: false }],
    planItems: [],
    aiUseAllowed: false,
    crossDomainUseAllowed: false,
    ...overrides,
  };
}

describe("planning editor draft serialization", () => {
  it("builds only the selected resource payload and does not leak other form fields", () => {
    const result = buildPlanningMutation(
      draft({ kind: "goal", regimenQuantity: "12", contextPriority: "50" }),
    );
    expect(result.ok).toBe(true);
    if (!result.ok || result.mutation.kind !== "goal") return;
    expect(result.mutation.create.goal).toEqual({
      label: "Move more",
      domain: "exercise",
      start_date: null,
      target_date: null,
      target: null,
      target_period: null,
    });
    expect(result.mutation.create).not.toHaveProperty("regimen");
    expect(result.mutation.create).not.toHaveProperty("context");
  });

  it("keeps zero targets and explicit false permissions in the request", () => {
    const result = buildPlanningMutation(
      draft({
        targetMetric: "duration",
        targetValue: "0",
        aiUseAllowed: false,
        crossDomainUseAllowed: false,
      }),
    );
    expect(result.ok).toBe(true);
    if (!result.ok || result.mutation.kind !== "goal") return;
    expect(result.mutation.create.goal.target?.value).toBe(0);
    expect(result.mutation.create).toMatchObject({
      ai_use_allowed: false,
      cross_domain_use_allowed: false,
    });
  });

  it("distinguishes blank regimen quantity from an entered zero", () => {
    const blank = buildPlanningMutation(draft({ kind: "regimen" }));
    const zero = buildPlanningMutation(
      draft({ kind: "regimen", regimenQuantity: "0" }),
    );
    expect(blank.ok && blank.mutation.kind === "regimen").toBe(true);
    expect(zero.ok && zero.mutation.kind === "regimen").toBe(true);
    if (
      !blank.ok ||
      blank.mutation.kind !== "regimen" ||
      !zero.ok ||
      zero.mutation.kind !== "regimen"
    )
      return;
    expect(blank.mutation.create.regimen.quantity).toBeNull();
    expect(zero.mutation.create.regimen.quantity).toEqual({
      value: 0,
      unit: "dose",
    });
  });

  it("keeps an omitted context priority distinct from explicit zero", () => {
    const blank = buildPlanningMutation(
      draft({ kind: "context", contextPriority: "" }),
    );
    const zero = buildPlanningMutation(
      draft({ kind: "context", contextPriority: "0" }),
    );
    if (
      !blank.ok ||
      blank.mutation.kind !== "context" ||
      !zero.ok ||
      zero.mutation.kind !== "context"
    )
      return;
    expect(blank.mutation.create.context).not.toHaveProperty("priority");
    expect(zero.mutation.create.context.priority).toBe(0);
  });

  it("preserves tracker false values and normalizes schema-specific inputs", () => {
    const result = buildPlanningMutation(
      draft({
        kind: "tracker_definition",
        fields: [
          {
            id: "  active  ",
            label: "  Active?  ",
            kind: "boolean",
            required: false,
            choices: ["stale choice"],
          },
        ],
      }),
    );
    expect(result.ok).toBe(true);
    if (!result.ok || result.mutation.kind !== "tracker_definition") return;
    expect(result.mutation.create.definition.fields[0]).toEqual({
      id: "active",
      label: "Active?",
      kind: "boolean",
      required: false,
      choices: [],
      unit: null,
    });
  });
});
