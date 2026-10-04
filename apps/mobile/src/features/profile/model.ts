import type { components } from "@personal-health/api-client";

export type ProfileItem = components["schemas"]["ProfileItemResponse"];
export type ProfilePayload = components["schemas"]["ProfilePayloadV1"];
export type ProfileValue = components["schemas"]["ProfileValue"];
export type ProfileKind = ProfilePayload["kind"];
export type ProfileCategory = ProfilePayload["category"];
export type ProfileUnit = components["schemas"]["ProfileUnit"];

export type ValueDraft =
  | { type: "unknown" }
  | { type: "text"; value: string }
  | { type: "boolean"; value: boolean | null }
  | { type: "number"; value: string }
  | { type: "quantity"; value: string; unit: ProfileUnit | "" }
  | { type: "text_list"; value: string };

export type ProfileDraft = {
  kind: ProfileKind;
  key: string;
  label: string;
  value: ValueDraft;
  valid_from: string;
  valid_to: string;
  notes: string;
  ai_use_allowed: boolean;
  cross_domain_use_allowed: boolean;
};

export type BuiltProfileFields = Omit<
  components["schemas"]["ProfileCreateRequest"],
  "id"
>;

export type BuildDraftResult =
  | { ok: true; fields: BuiltProfileFields }
  | { ok: false; error: string };

export const PROFILE_CATEGORIES: {
  value: ProfileCategory;
  label: string;
  kind: ProfileKind;
}[] = [
  { value: "background", label: "Background", kind: "fact" },
  { value: "constraints", label: "Constraints", kind: "constraint" },
  { value: "preferences", label: "Preferences", kind: "preference" },
];

export const PROFILE_UNITS: ProfileUnit[] = [
  "kg",
  "g",
  "lb",
  "mg",
  "mcg",
  "ml",
  "l",
  "cm",
  "m",
  "in",
  "mmHg",
  "bpm",
  "%",
  "day",
  "week",
  "year",
  "dose",
];

export const EMPTY_PROFILE_DRAFT: ProfileDraft = {
  kind: "fact",
  key: "",
  label: "",
  value: { type: "unknown" },
  valid_from: "",
  valid_to: "",
  notes: "",
  ai_use_allowed: false,
  cross_domain_use_allowed: false,
};

export function categoryForKind(kind: ProfileKind): ProfileCategory {
  return PROFILE_CATEGORIES.find((category) => category.kind === kind)!.value;
}

function parseInstant(value: string, label: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (!/(?:Z|[+-]\d{2}:\d{2})$/i.test(trimmed)) {
    throw new Error(
      `${label} must include a timezone, such as 2026-10-03T12:00:00Z.`,
    );
  }
  const instant = new Date(trimmed);
  if (Number.isNaN(instant.getTime()))
    throw new Error(`${label} is not a valid date and time.`);
  return instant.toISOString();
}

function parseNumber(value: string, label: string): number {
  const trimmed = value.trim();
  if (!trimmed) throw new Error(`${label} is required, or choose Unknown.`);
  const number = Number(trimmed);
  if (!Number.isFinite(number))
    throw new Error(`${label} must be a finite number.`);
  return number;
}

function buildValue(draft: ValueDraft): ProfileValue | null {
  switch (draft.type) {
    case "unknown":
      return null;
    case "text":
      if (draft.value.length > 2000)
        throw new Error("Text values can be at most 2,000 characters.");
      return { type: "text", value: draft.value };
    case "boolean":
      return draft.value === null
        ? null
        : { type: "boolean", value: draft.value };
    case "number":
      return { type: "number", value: parseNumber(draft.value, "Number") };
    case "quantity":
      if (!draft.unit) throw new Error("Choose a unit for this quantity.");
      return {
        type: "quantity",
        value: parseNumber(draft.value, "Quantity"),
        unit: draft.unit,
      };
    case "text_list": {
      const values = draft.value
        .split("\n")
        .map((entry) => entry.trim())
        .filter((entry) => entry.length > 0);
      if (values.length > 50)
        throw new Error("Lists can contain at most 50 entries.");
      if (values.some((entry) => entry.length > 200)) {
        throw new Error("Each list entry can be at most 200 characters.");
      }
      return { type: "text_list", value: values };
    }
  }
}

export function buildProfileFields(draft: ProfileDraft): BuildDraftResult {
  const label = draft.label.trim();
  const key = draft.key.trim();
  if (!label)
    return { ok: false, error: "Enter a label for this Profile item." };
  if (label.length > 120)
    return { ok: false, error: "Labels can be at most 120 characters." };
  if (!/^[a-z][a-z0-9_]{0,63}$/.test(key)) {
    return {
      ok: false,
      error:
        "The key must start with a lowercase letter and use only lowercase letters, numbers, and underscores.",
    };
  }

  try {
    const value = buildValue(draft.value);
    const valid_from = parseInstant(draft.valid_from, "Effective start");
    const valid_to = parseInstant(draft.valid_to, "Effective end");
    if (valid_from && valid_to && new Date(valid_from) >= new Date(valid_to)) {
      throw new Error("Effective start must be earlier than effective end.");
    }
    const profile: ProfilePayload = {
      kind: draft.kind,
      category: categoryForKind(draft.kind),
      key,
      label,
      value,
    };
    const fields: BuiltProfileFields = {
      profile,
      valid_from,
      valid_to,
      ai_use_allowed: draft.ai_use_allowed,
      cross_domain_use_allowed: draft.cross_domain_use_allowed,
      notes: draft.notes.trim() || null,
    };
    return { ok: true, fields };
  } catch (error) {
    return {
      ok: false,
      error:
        error instanceof Error
          ? error.message
          : "Check the Profile fields and try again.",
    };
  }
}

export function valueDraftFromProfile(
  value: ProfilePayload["value"],
): ValueDraft {
  if (value === null) return { type: "unknown" };
  switch (value.type) {
    case "text":
      return { type: "text", value: value.value };
    case "boolean":
      return { type: "boolean", value: value.value };
    case "number":
      return { type: "number", value: String(value.value) };
    case "quantity":
      return { type: "quantity", value: String(value.value), unit: value.unit };
    case "text_list":
      return { type: "text_list", value: value.value.join("\n") };
  }
}

export function draftFromProfile(item: ProfileItem): ProfileDraft {
  return {
    kind: item.profile.kind,
    key: item.profile.key,
    label: item.profile.label,
    value: valueDraftFromProfile(item.profile.value),
    valid_from: item.valid_from ?? "",
    valid_to: item.valid_to ?? "",
    notes: item.notes ?? "",
    ai_use_allowed: item.permissions.ai_use_allowed,
    cross_domain_use_allowed: item.permissions.cross_domain_use_allowed,
  };
}

export function formatProfileValue(value: ProfilePayload["value"]): string {
  if (value === null) return "Unknown / not provided";
  switch (value.type) {
    case "text":
      return value.value || "Blank text";
    case "boolean":
      return value.value ? "Yes" : "No";
    case "number":
      return String(value.value);
    case "quantity":
      return `${value.value} ${value.unit}`;
    case "text_list":
      return value.value.length ? value.value.join(", ") : "No entries";
  }
}

export function formatInstant(value: string | null): string {
  if (!value) return "No date set";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function newProfileId(): string {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(
    /[xy]/g,
    (character) => {
      const random = Math.floor(Math.random() * 16);
      return (character === "x" ? random : (random & 0x3) | 0x8).toString(16);
    },
  );
}
