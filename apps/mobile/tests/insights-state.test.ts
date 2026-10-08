import { describe, expect, it } from "vitest";

import {
  evidenceDestination,
  formatInsightValue,
  isCurrentInsightsRequest,
} from "../src/features/insights/state";

describe("Insights query and evidence state", () => {
  it("rejects a stale result after the query, focus, session, or request changes", () => {
    const request = {
      screenGeneration: 3,
      requestGeneration: 6,
      sessionEpoch: 4,
      queryKey: "metric-a|week-1",
    };
    expect(isCurrentInsightsRequest(request, request)).toBe(true);
    expect(
      isCurrentInsightsRequest(
        { ...request, queryKey: "metric-b|week-1" },
        request,
      ),
    ).toBe(false);
    expect(
      isCurrentInsightsRequest({ ...request, screenGeneration: 4 }, request),
    ).toBe(false);
    expect(
      isCurrentInsightsRequest({ ...request, sessionEpoch: 5 }, request),
    ).toBe(false);
    expect(
      isCurrentInsightsRequest({ ...request, requestGeneration: 7 }, request),
    ).toBe(false);
  });

  it("keeps evidence navigation bound to the exact source object and revision", () => {
    expect(
      evidenceDestination({
        object_type: "derived_signal",
        object_id: "signal-1",
        revision: 8,
      }),
    ).toEqual({
      pathname: "/analytics/evidence/[objectId]",
      params: { objectId: "signal-1", revision: "8" },
    });
    expect(
      evidenceDestination({
        object_type: "event",
        object_id: "event-1",
        revision: 2,
      }),
    ).toEqual({
      pathname: "/daily/item/[itemId]/history",
      params: { itemId: "event-1", type: "event", revision: "2" },
    });
  });

  it("renders missing metrics as unknown without converting zero to missing", () => {
    expect(formatInsightValue(null, "min")).toBe("No known values");
    expect(formatInsightValue(0, "min")).toBe("0 min");
  });
});
