import type { components } from "@personal-health/api-client";

export type TrackerField = components["schemas"]["TrackerFieldV1"];
export type TrackerInputMap = Record<string, string | boolean>;
export type TrackerValue =
  | string
  | boolean
  | number
  | { value: number; unit: string };

export function collectTrackerValues(
  fields: TrackerField[],
  inputs: TrackerInputMap,
): Record<string, TrackerValue> {
  const values: Record<string, TrackerValue> = {};
  for (const field of fields) {
    const raw = inputs[field.id];
    const normalized = typeof raw === "string" ? raw.trim() : raw;
    if (normalized === undefined || normalized === "") {
      if (field.required) throw new Error(`${field.label} is required.`);
      continue;
    }
    if (field.kind === "boolean") {
      if (typeof normalized !== "boolean")
        throw new Error(`${field.label} needs a yes or no value.`);
      values[field.id] = normalized;
    } else if (field.kind === "number" || field.kind === "quantity") {
      if (typeof normalized !== "string")
        throw new Error(`${field.label} needs a number.`);
      const number = Number(normalized);
      if (!Number.isFinite(number) || Math.abs(number) > 1e300) {
        throw new Error(`${field.label} needs a finite number.`);
      }
      values[field.id] =
        field.kind === "quantity"
          ? { value: number, unit: field.unit ?? "dose" }
          : number;
    } else {
      if (typeof normalized !== "string")
        throw new Error(`${field.label} needs text.`);
      if (
        field.kind === "enum" &&
        !(field.choices ?? []).includes(normalized)
      ) {
        throw new Error(`Choose a value for ${field.label}.`);
      }
      if (field.kind === "date" && !/^\d{4}-\d{2}-\d{2}$/.test(normalized)) {
        throw new Error(`${field.label} must use YYYY-MM-DD.`);
      }
      if (field.kind === "text" && normalized.length > 2000) {
        throw new Error(`${field.label} can be at most 2,000 characters.`);
      }
      values[field.id] = normalized;
    }
  }
  return values;
}

export function setTrackerInput(
  current: TrackerInputMap,
  id: string,
  value: string | boolean | undefined,
): TrackerInputMap {
  if (value === undefined) {
    const next = { ...current };
    delete next[id];
    return next;
  }
  return { ...current, [id]: value };
}

export function nextTrackerFieldId(fields: TrackerField[]): string {
  const used = new Set(fields.map((field) => field.id.trim()));
  let suffix = 1;
  while (used.has(`field_${suffix}`)) suffix += 1;
  return `field_${suffix}`;
}
