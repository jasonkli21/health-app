import { describe, expect, it } from "vitest";
import type { PlanningItem } from "../src/features/planning/api";
import { canAdvancePlanningRevision } from "../src/features/planning/editState";

function goal(
  revision: number,
): Extract<PlanningItem, { object_type: "goal" }> {
  return {
    id: "goal-1",
    object_type: "goal",
    domain: "exercise",
    status: "active",
    title: "Move more",
    valid_from: null,
    valid_to: null,
    recorded_at: "2026-10-05T12:00:00Z",
    created_at: "2026-10-05T12:00:00Z",
    updated_at: "2026-10-05T12:00:00Z",
    source: { id: "manual-1", kind: "manual", name: "Manual entry" },
    confirmation_status: "user_confirmed",
    schema_version: 1,
    revision,
    notes: null,
    lifecycle: "active",
    ai_use_allowed: true,
    cross_domain_use_allowed: false,
    goal: {
      label: "Move more",
      domain: "exercise",
      target: null,
      start_date: null,
      target_date: null,
    },
  };
}

describe("planning editor revision refresh", () => {
  it("accepts schedule-only revisions while preserving an unsaved draft", () => {
    expect(canAdvancePlanningRevision(goal(1), goal(2))).toBe(true);
  });

  it("does not attach a stale draft to a revision with different content", () => {
    const incoming = goal(2);
    incoming.goal.label = "Changed elsewhere";
    expect(canAdvancePlanningRevision(goal(1), incoming)).toBe(false);
  });

  it("requires an explicit reload when permission is revoked", () => {
    const incoming = { ...goal(2), ai_use_allowed: false };
    expect(canAdvancePlanningRevision(goal(1), incoming)).toBe(false);
  });

  it("requires an explicit reload for changed notes or lifecycle", () => {
    expect(
      canAdvancePlanningRevision(goal(1), { ...goal(2), notes: "New notes" }),
    ).toBe(false);
    expect(
      canAdvancePlanningRevision(goal(1), { ...goal(2), lifecycle: "paused" }),
    ).toBe(false);
  });

  it("never advances a draft to another resource", () => {
    expect(
      canAdvancePlanningRevision(goal(1), { ...goal(2), id: "goal-2" }),
    ).toBe(false);
  });
});
