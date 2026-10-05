import { describe, expect, it } from "vitest";

import { ApiError } from "@personal-health/api-client";
import {
  isDailyCreateAttemptCurrent,
  type DailyCreateAttempt,
} from "../src/features/daily/api";
import {
  PlanningCreateRecovery,
  type PlanningCreateAttempt,
} from "../src/features/planning/api";

const goalAttempt = (): Extract<PlanningCreateAttempt, { kind: "goal" }> => ({
  kind: "goal",
  body: {
    id: "00000000-0000-0000-0000-000000000101",
    goal: {
      label: "Move more",
      domain: "exercise",
      target: null,
      target_period: null,
      start_date: null,
      target_date: null,
    },
    ai_use_allowed: false,
    cross_domain_use_allowed: false,
  },
  sessionEpoch: 4,
  sessionUserId: "owner-a",
});

describe("planning create uncertainty recovery", () => {
  it("reuses the same owner-scoped ID and canonical body after an uncertain response", () => {
    const recovery = new PlanningCreateRecovery();
    const attempt = goalAttempt();

    expect(recovery.markFailure(attempt, new Error("response lost"))).toBe(
      true,
    );
    expect(recovery.prepare(goalAttempt())).toBe(attempt);
    expect(recovery.retryOriginal()?.body.id).toBe(attempt.body.id);
  });

  it("blocks changed content and rejects replay under another owner or session", () => {
    const recovery = new PlanningCreateRecovery();
    const attempt = goalAttempt();
    recovery.markFailure(attempt, new Error("response lost"));

    expect(() =>
      recovery.prepare({
        ...goalAttempt(),
        body: {
          ...goalAttempt().body,
          goal: { ...goalAttempt().body.goal, label: "Changed draft" },
        },
      }),
    ).toThrow("Retry the original planning save");
    expect(() =>
      recovery.prepare({
        ...goalAttempt(),
        sessionEpoch: 5,
        sessionUserId: "owner-b",
      }),
    ).toThrow("previous account's save");
  });

  it("clears recovery only for a definitive rejection", () => {
    const recovery = new PlanningCreateRecovery();
    const attempt = goalAttempt();
    expect(recovery.markFailure(attempt, new ApiError(422))).toBe(false);
    expect(recovery.retryOriginal()).toBeNull();
  });
});

describe("session-scoped daily create attempts", () => {
  it("rejects delayed continuations after account or epoch changes", () => {
    const attempt: DailyCreateAttempt = {
      request: { events: [], observations: [], links: [] },
      primaryId: "entry-a",
      domain: "nutrition",
      draft: {} as DailyCreateAttempt["draft"],
      sessionEpoch: 4,
      sessionUserId: "owner-a",
    };
    expect(
      isDailyCreateAttemptCurrent(attempt, { epoch: 4, userId: "owner-a" }),
    ).toBe(true);
    expect(
      isDailyCreateAttemptCurrent(attempt, { epoch: 6, userId: "owner-b" }),
    ).toBe(false);
    expect(
      isDailyCreateAttemptCurrent(attempt, { epoch: 6, userId: "owner-a" }),
    ).toBe(false);
  });
});
