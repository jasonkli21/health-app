import { describe, expect, it } from "vitest";
import type { components } from "@personal-health/api-client";

import {
  collectTrackerValues,
  nextTrackerFieldId,
  setTrackerInput,
} from "../src/features/planning/trackerEntry";

type Field = components["schemas"]["TrackerFieldV1"];

const numberField: Field = {
  id: "amount",
  label: "Amount",
  kind: "number",
  required: false,
  unit: null,
  choices: [],
};

describe("custom tracker input normalization", () => {
  it("omits optional blank numeric values without fabricating zero", () => {
    expect(collectTrackerValues([numberField], { amount: "   " })).toEqual({});
  });

  it("rejects whitespace for required numbers and preserves explicit zero and false", () => {
    expect(() =>
      collectTrackerValues([{ ...numberField, required: true }], {
        amount: "  ",
      }),
    ).toThrow("Amount is required.");

    const fields: Field[] = [
      numberField,
      {
        id: "enabled",
        label: "Enabled",
        kind: "boolean",
        required: false,
        unit: null,
        choices: [],
      },
    ];
    expect(
      collectTrackerValues(fields, { amount: "0", enabled: false }),
    ).toEqual({
      amount: 0,
      enabled: false,
    });
  });

  it("allows optional selections to return to absent", () => {
    expect(
      setTrackerInput({ enabled: false, amount: "0" }, "enabled", undefined),
    ).toEqual({
      amount: "0",
    });
  });

  it("allocates unused stable field IDs after removal and user edits", () => {
    const fields: Field[] = [
      { ...numberField, id: "value" },
      { ...numberField, id: "field_3" },
    ];
    const next = nextTrackerFieldId(fields);
    expect(next).not.toBe("field_3");
    expect(new Set([...fields.map((field) => field.id), next]).size).toBe(3);
  });
});
