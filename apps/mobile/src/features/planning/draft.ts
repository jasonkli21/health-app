import type { components } from "@personal-health/api-client";

import type { PlanningCreateAttempt, PlanningItem } from "./api";

export type PlanningKind =
  | "goal"
  | "regimen"
  | "plan"
  | "context"
  | "tracker_definition";
export type TrackerField = components["schemas"]["TrackerFieldV1"];

export const GOAL_METRICS_BY_DOMAIN: Record<string, readonly string[]> = {
  general: [],
  nutrition: ["energy"],
  exercise: ["duration", "distance"],
  sleep: ["duration"],
  symptoms: ["symptom_severity", "symptom_episode_count"],
  measurements: [
    "weight",
    "temperature",
    "systolic_pressure",
    "diastolic_pressure",
    "pulse",
  ],
};

export const GOAL_UNITS: Record<string, readonly string[]> = {
  energy: ["kcal", "kJ"],
  duration: ["min", "h"],
  distance: ["m", "km", "mi"],
  weight: ["kg", "lb"],
  temperature: ["C", "F"],
  systolic_pressure: ["mmHg"],
  diastolic_pressure: ["mmHg"],
  pulse: ["bpm"],
  symptom_severity: ["score"],
  symptom_episode_count: ["episodes"],
};

export interface PlanningEditorDraft {
  kind: PlanningKind;
  id: string;
  original: PlanningItem | null;
  label: string;
  domain: string;
  category: string;
  startDate: string;
  endDate: string;
  targetDate: string;
  targetMetric: string;
  targetComparator: string;
  targetValue: string;
  targetUnit: string;
  targetPeriod: string;
  regimenQuantity: string;
  regimenUnit: string;
  regimenInstructions: string;
  contextNotes: string;
  contextPriority: string;
  contextRelated: components["schemas"]["ContextRelation"][];
  fields: TrackerField[];
  planItems: components["schemas"]["PlanItemInput"][];
  aiUseAllowed: boolean;
  crossDomainUseAllowed: boolean;
}

export type PlanningMutation =
  | {
      kind: "goal";
      create: Extract<PlanningCreateAttempt, { kind: "goal" }>["body"];
      update: components["schemas"]["GoalUpdateRequest"];
    }
  | {
      kind: "regimen";
      create: Extract<PlanningCreateAttempt, { kind: "regimen" }>["body"];
      update: components["schemas"]["RegimenUpdateRequest"];
    }
  | {
      kind: "plan";
      create: Extract<PlanningCreateAttempt, { kind: "plan" }>["body"];
      update: components["schemas"]["PlanUpdateRequest"];
    }
  | {
      kind: "context";
      create: Extract<PlanningCreateAttempt, { kind: "context" }>["body"];
      update: components["schemas"]["ContextUpdateRequest"];
    }
  | {
      kind: "tracker_definition";
      create: Extract<
        PlanningCreateAttempt,
        { kind: "tracker_definition" }
      >["body"];
      update: components["schemas"]["TrackerUpdateRequest"];
    };

export type PlanningDraftResult =
  | { ok: true; mutation: PlanningMutation }
  | { ok: false; error: string };

export function planningCreateAttempt(
  mutation: PlanningMutation,
  session: { epoch: number; userId: string | null },
): PlanningCreateAttempt {
  const identity = {
    sessionEpoch: session.epoch,
    sessionUserId: session.userId,
  };
  switch (mutation.kind) {
    case "goal":
      return { kind: mutation.kind, body: mutation.create, ...identity };
    case "regimen":
      return { kind: mutation.kind, body: mutation.create, ...identity };
    case "plan":
      return { kind: mutation.kind, body: mutation.create, ...identity };
    case "context":
      return { kind: mutation.kind, body: mutation.create, ...identity };
    case "tracker_definition":
      return { kind: mutation.kind, body: mutation.create, ...identity };
  }
}

function validCalendarDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return (
    Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value
  );
}

function invalid(error: string): PlanningDraftResult {
  return { ok: false, error };
}

export function buildPlanningMutation(
  draft: PlanningEditorDraft,
): PlanningDraftResult {
  if (!draft.label.trim()) return invalid("Enter a name before saving.");
  const dates =
    draft.kind === "goal"
      ? [draft.startDate, draft.targetDate]
      : ["regimen", "plan", "context"].includes(draft.kind)
        ? [draft.startDate, draft.endDate]
        : [];
  if (dates.some((value) => value && !validCalendarDate(value))) {
    return invalid("Dates must be real calendar dates in YYYY-MM-DD format.");
  }
  if (draft.startDate && draft.endDate && draft.endDate < draft.startDate) {
    return invalid("The end date must be on or after the start date.");
  }
  if (
    draft.startDate &&
    draft.targetDate &&
    draft.targetDate < draft.startDate
  ) {
    return invalid("The target date must be on or after the start date.");
  }

  const expectedRevision = draft.original?.revision ?? 0;
  if (draft.kind === "goal") {
    let target: components["schemas"]["MetricTarget"] | null = null;
    if (draft.targetMetric !== "none") {
      const numericTarget = Number(draft.targetValue);
      if (
        !draft.targetValue.trim() ||
        !Number.isFinite(numericTarget) ||
        numericTarget < 0
      ) {
        return invalid("Enter a nonnegative finite value for the goal target.");
      }
      if (
        !(GOAL_METRICS_BY_DOMAIN[draft.domain] ?? []).includes(
          draft.targetMetric,
        )
      ) {
        return invalid(
          "Choose a target metric that belongs to this goal domain.",
        );
      }
      target = {
        metric: draft.targetMetric as components["schemas"]["MetricKey"],
        comparator:
          draft.targetComparator as components["schemas"]["GoalComparator"],
        value: numericTarget,
        unit: draft.targetUnit as components["schemas"]["MeasurementUnit"],
      };
    }
    const goal: components["schemas"]["GoalPayloadV1"] = {
      ...(draft.original?.object_type === "goal" ? draft.original.goal : {}),
      label: draft.label.trim(),
      domain: draft.domain as components["schemas"]["GoalDomain"],
      start_date: draft.startDate || null,
      target_date: draft.targetDate || null,
      target,
      target_period: target
        ? (draft.targetPeriod as components["schemas"]["GoalPayloadV1"]["target_period"])
        : null,
    };
    return {
      ok: true,
      mutation: {
        kind: "goal",
        create: {
          id: draft.id,
          goal,
          ai_use_allowed: draft.aiUseAllowed,
          cross_domain_use_allowed: draft.crossDomainUseAllowed,
        },
        update: {
          expected_revision: expectedRevision,
          goal,
          ai_use_allowed: draft.aiUseAllowed,
          cross_domain_use_allowed: draft.crossDomainUseAllowed,
        },
      },
    };
  }

  if (draft.kind === "regimen") {
    const quantityValue = draft.regimenQuantity.trim()
      ? Number(draft.regimenQuantity)
      : null;
    if (
      quantityValue !== null &&
      (!Number.isFinite(quantityValue) || quantityValue < 0)
    ) {
      return invalid("Enter a nonnegative finite regimen quantity.");
    }
    if (draft.regimenInstructions.length > 2000) {
      return invalid("Instructions can be at most 2,000 characters.");
    }
    const regimen: components["schemas"]["RegimenPayloadV1"] = {
      ...(draft.original?.object_type === "regimen"
        ? draft.original.regimen
        : {}),
      label: draft.label.trim(),
      kind: draft.category as components["schemas"]["RegimenKind"],
      domain: draft.domain as components["schemas"]["GoalDomain"],
      start_date: draft.startDate || null,
      end_date: draft.endDate || null,
      instructions: draft.regimenInstructions.trim() || null,
      quantity:
        quantityValue === null
          ? null
          : {
              value: quantityValue,
              unit: draft.regimenUnit as components["schemas"]["ProfileUnit"],
            },
    };
    return {
      ok: true,
      mutation: {
        kind: "regimen",
        create: {
          id: draft.id,
          regimen,
          ai_use_allowed: draft.aiUseAllowed,
          cross_domain_use_allowed: draft.crossDomainUseAllowed,
        },
        update: {
          expected_revision: expectedRevision,
          regimen,
          ai_use_allowed: draft.aiUseAllowed,
          cross_domain_use_allowed: draft.crossDomainUseAllowed,
        },
      },
    };
  }

  if (draft.kind === "plan") {
    const plan: components["schemas"]["PlanPayloadV1"] = {
      ...(draft.original?.object_type === "plan" ? draft.original.plan : {}),
      label: draft.label.trim(),
      items: draft.planItems,
      start_date: draft.startDate || null,
      end_date: draft.endDate || null,
    };
    return {
      ok: true,
      mutation: {
        kind: "plan",
        create: {
          id: draft.id,
          plan,
          ai_use_allowed: draft.aiUseAllowed,
          cross_domain_use_allowed: draft.crossDomainUseAllowed,
        },
        update: {
          expected_revision: expectedRevision,
          plan,
          ai_use_allowed: draft.aiUseAllowed,
          cross_domain_use_allowed: draft.crossDomainUseAllowed,
        },
      },
    };
  }

  if (draft.kind === "context") {
    const priority = draft.contextPriority.trim()
      ? Number(draft.contextPriority)
      : undefined;
    if (
      priority !== undefined &&
      (!Number.isInteger(priority) || priority < 0 || priority > 100)
    ) {
      return invalid(
        "Context priority must be a whole number from 0 through 100.",
      );
    }
    if (draft.contextNotes.length > 2000 || draft.contextRelated.length > 20) {
      return invalid("Context notes or linked items exceed the allowed limit.");
    }
    const context: components["schemas"]["ContextPayloadV1"] = {
      ...(draft.original?.object_type === "context"
        ? draft.original.context
        : {}),
      label: draft.label.trim(),
      context_type: draft.category as components["schemas"]["ContextType"],
      ...(priority !== undefined ? { priority } : {}),
      notes: draft.contextNotes.trim() || null,
      start_at: draft.startDate || null,
      end_at: draft.endDate || null,
      related: draft.contextRelated,
    };
    return {
      ok: true,
      mutation: {
        kind: "context",
        create: {
          id: draft.id,
          context,
          ai_use_allowed: draft.aiUseAllowed,
          cross_domain_use_allowed: draft.crossDomainUseAllowed,
        },
        update: {
          expected_revision: expectedRevision,
          context,
          ai_use_allowed: draft.aiUseAllowed,
          cross_domain_use_allowed: draft.crossDomainUseAllowed,
        },
      },
    };
  }

  if (
    draft.fields.length === 0 ||
    draft.fields.some((field) => !field.id.trim() || !field.label.trim())
  ) {
    return invalid("Each tracker field needs an ID and label.");
  }
  const definition: components["schemas"]["TrackerDefinitionV1"] = {
    name: draft.label.trim(),
    domain: draft.domain as components["schemas"]["DailyDomain"],
    fields: draft.fields.map((field) => ({
      ...field,
      id: field.id.trim(),
      label: field.label.trim(),
      choices: field.kind === "enum" ? (field.choices ?? []) : [],
      unit: field.kind === "quantity" ? (field.unit ?? "dose") : null,
    })),
  };
  return {
    ok: true,
    mutation: {
      kind: "tracker_definition",
      create: {
        id: draft.id,
        definition,
        ai_use_allowed: draft.aiUseAllowed,
        cross_domain_use_allowed: draft.crossDomainUseAllowed,
      },
      update: {
        expected_revision: expectedRevision,
        definition,
        ai_use_allowed: draft.aiUseAllowed,
        cross_domain_use_allowed: draft.crossDomainUseAllowed,
      },
    },
  };
}
