import { ApiError } from "@personal-health/api-client";
import { describe, expect, it } from "vitest";

import { DailyCreateRecovery } from "../src/features/daily/api";
import {
  buildDailyCreateRequest,
  emptyDailyDraft,
} from "../src/features/daily/model";

const ids = {
  event: "00000000-0000-0000-0000-000000000011",
  observation: "00000000-0000-0000-0000-000000000012",
  secondObservation: "00000000-0000-0000-0000-000000000013",
};

function attempt(label: string) {
  const draft = { ...emptyDailyDraft(new Date("2026-05-01T16:00:00Z")), label };
  const built = buildDailyCreateRequest("nutrition", draft, ids);
  if (!built.ok) throw new Error(built.error);
  return {
    request: built.value,
    primaryId: ids.event,
    domain: "nutrition" as const,
    draft,
  };
}

describe("daily create recovery", () => {
  it("keeps the original IDs and body after an uncertain response and blocks changed details", () => {
    const recovery = new DailyCreateRecovery();
    const original = attempt("Lunch");
    const prepared = recovery.prepare(original);
    expect(recovery.markFailure(prepared, new TypeError("response lost"))).toBe(
      true,
    );
    expect(recovery.retryOriginal()).toEqual(original);
    expect(() => recovery.prepare(attempt("Updated lunch"))).toThrow(
      "Retry the original save",
    );
    expect(recovery.prepare(attempt("Lunch"))).toEqual(original);
  });

  it("allows a corrected body after a definitive validation or ID conflict", () => {
    const recovery = new DailyCreateRecovery();
    const rejected = attempt("Lunch");
    expect(recovery.markFailure(rejected, new ApiError(422))).toBe(false);
    expect(recovery.isUncertain).toBe(false);
    expect(
      recovery.prepare(attempt("Lunch and fruit")).request.events?.[0]?.event
        .payload,
    ).toMatchObject({
      kind: "meal",
      label: "Lunch and fruit",
    });
    expect(recovery.markFailure(rejected, new ApiError(409))).toBe(false);
    expect(recovery.isUncertain).toBe(false);
  });

  it("keeps server errors uncertain until the original save is retried", () => {
    const recovery = new DailyCreateRecovery();
    const original = attempt("Lunch");
    expect(recovery.markFailure(original, new ApiError(503))).toBe(true);
    expect(recovery.retryOriginal()).toEqual(original);
    recovery.resolve();
    expect(recovery.isUncertain).toBe(false);
  });
});
