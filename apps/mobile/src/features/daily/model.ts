import type { components } from "@personal-health/api-client";

export type DailyDomain = components["schemas"]["DailyDomain"];
export type DailyEvent = components["schemas"]["DailyEventResponse"];
export type DailyObservation =
  components["schemas"]["DailyObservationResponse"];
export type DailyItem = DailyEvent | DailyObservation;
export type EventRecord = components["schemas"]["EventSchemaV1"];
export type ObservationRecord = components["schemas"]["ObservationSchemaV1"];
export type CustomTrackerValue = components["schemas"]["CustomTrackerValueV1"];
export type DailyCreateRequest =
  components["schemas"]["DailyEntryCreateRequest"];

export const DAILY_DOMAINS: { value: DailyDomain; label: string }[] = [
  { value: "nutrition", label: "Meal" },
  { value: "exercise", label: "Workout" },
  { value: "sleep", label: "Sleep" },
  { value: "symptoms", label: "Symptom" },
  { value: "measurements", label: "Measurement" },
];

export type MeasurementMetric =
  | "weight"
  | "temperature"
  | "systolic_pressure"
  | "diastolic_pressure"
  | "pulse"
  | "blood_pressure";

export type DailyDraft = {
  label: string;
  precision: "instant" | "date_only";
  instant: string;
  localDate: string;
  timezone: string;
  endedAt: string;
  foods: string;
  energyValue: string;
  energyUnit: "kcal" | "kJ";
  durationValue: string;
  durationUnit: "min" | "h";
  distanceValue: string;
  distanceUnit: "m" | "km" | "mi";
  quality: string;
  severity: string;
  measurementMetric: MeasurementMetric;
  measurementValue: string;
  systolicValue: string;
  diastolicValue: string;
  measurementUnit: "kg" | "lb" | "C" | "F" | "mmHg" | "bpm";
  notes: string;
  aiUseAllowed: boolean;
};

export type BuildResult<T> =
  | { ok: true; value: T }
  | { ok: false; error: string };

export const DEVICE_TIMEZONE =
  Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";

export function newDailyId(): string {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(
    /[xy]/g,
    (character) => {
      const random = Math.floor(Math.random() * 16);
      return (character === "x" ? random : (random & 0x3) | 0x8).toString(16);
    },
  );
}

export function localCalendarDate(now = new Date()): string {
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function emptyDailyDraft(now = new Date()): DailyDraft {
  return {
    label: "",
    precision: "instant",
    instant: now.toISOString().replace(/\.\d{3}Z$/, "Z"),
    localDate: localCalendarDate(now),
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
    endedAt: "",
    foods: "",
    energyValue: "",
    energyUnit: "kcal",
    durationValue: "",
    durationUnit: "min",
    distanceValue: "",
    distanceUnit: "km",
    quality: "",
    severity: "",
    measurementMetric: "weight",
    measurementValue: "",
    systolicValue: "",
    diastolicValue: "",
    measurementUnit: "kg",
    notes: "",
    aiUseAllowed: false,
  };
}

function calendarDate(value: string, label: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value.trim());
  if (!match) throw new Error(`${label} must use YYYY-MM-DD.`);
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (
    year < 1 ||
    month < 1 ||
    month > 12 ||
    day < 1 ||
    day > days[month - 1]!
  ) {
    throw new Error(`${label} is not a valid calendar date.`);
  }
  return value.trim();
}

function instant(value: string, label: string): string {
  const trimmed = value.trim();
  const match =
    /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?(Z|([+-])(\d{2}):(\d{2}))$/i.exec(
      trimmed,
    );
  if (!match) {
    throw new Error(
      `${label} needs an ISO date and time with Z or a UTC offset.`,
    );
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4]);
  const minute = Number(match[5]);
  const second = Number(match[6]);
  const offsetHour = Number(match[10] ?? 0);
  const offsetMinute = Number(match[11] ?? 0);
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (
    year < 1 ||
    month < 1 ||
    month > 12 ||
    day < 1 ||
    day > days[month - 1]! ||
    hour > 23 ||
    minute > 59 ||
    second > 59 ||
    offsetHour > 23 ||
    offsetMinute > 59
  ) {
    throw new Error(`${label} is not a valid calendar time.`);
  }
  const parsed = new Date(trimmed);
  if (Number.isNaN(parsed.getTime()))
    throw new Error(`${label} is not a valid date and time.`);
  return match[8]?.toUpperCase() === "Z"
    ? trimmed.replace(/z$/i, "Z")
    : trimmed;
}

function instantMicroseconds(value: string): bigint {
  const match = /\.(\d{1,6})(?:Z|[+-]\d{2}:\d{2})$/i.exec(value);
  const fraction = (match?.[1] ?? "").padEnd(6, "0");
  const milliseconds = BigInt(new Date(value).getTime());
  return milliseconds * 1000n + BigInt(fraction.slice(3) || "0");
}

function validTimezone(value: string): string {
  const timezone = value.trim();
  if (!timezone || timezone.length > 64)
    throw new Error("Enter an IANA timezone name.");
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: timezone }).format();
  } catch {
    throw new Error("Enter a valid IANA timezone name.");
  }
  return timezone;
}

function finiteOptional(
  value: string,
  label: string,
  minimum = -Infinity,
): number | null {
  if (!value.trim()) return null;
  const result = Number(value.trim());
  if (!Number.isFinite(result) || result < minimum) {
    throw new Error(
      `${label} must be a finite number${minimum === 0 ? " at least zero" : ""}.`,
    );
  }
  return result;
}

function timePoint(draft: DailyDraft): components["schemas"]["DailyTimePoint"] {
  const timezone = validTimezone(draft.timezone);
  if (draft.precision === "date_only") {
    return {
      precision: "date_only",
      local_date: calendarDate(draft.localDate, "Date"),
      timezone,
    };
  }
  return {
    precision: "instant",
    occurred_at: instant(draft.instant, "Time"),
    timezone,
  };
}

function intervalEnd(
  draft: DailyDraft,
  time: components["schemas"]["DailyTimePoint"],
  label: string,
): string | null {
  if (!draft.endedAt.trim()) return null;
  if (time.precision !== "instant") {
    throw new Error(`${label} needs an exact start time.`);
  }
  const endedAt = instant(draft.endedAt, label);
  if (instantMicroseconds(endedAt) <= instantMicroseconds(time.occurred_at)) {
    throw new Error(`${label} must be after the start time.`);
  }
  return endedAt;
}

function buildEvent(domain: DailyDomain, draft: DailyDraft): EventRecord {
  const label = draft.label.trim() || (domain === "sleep" ? "Sleep" : "");
  if (!label) throw new Error("Enter a label for this entry.");
  if (label.length > 120)
    throw new Error("Labels can be at most 120 characters.");
  if (draft.notes.length > 2000)
    throw new Error("Notes can be at most 2,000 characters.");
  const time = timePoint(draft);
  const notes = draft.notes.trim() || null;

  if (domain === "nutrition") {
    const energy = finiteOptional(draft.energyValue, "Energy", 0);
    const foods = draft.foods
      .split(/[\n,]/)
      .map((food) => food.trim())
      .filter(Boolean);
    if (foods.length > 20 || foods.some((food) => food.length > 120)) {
      throw new Error("Enter up to 20 foods, each at most 120 characters.");
    }
    return {
      domain,
      time,
      ended_at: intervalEnd(draft, time, "End time"),
      payload: {
        kind: "meal",
        label,
        foods,
        energy:
          energy === null ? null : { value: energy, unit: draft.energyUnit },
      },
      notes,
    };
  }

  if (domain === "exercise") {
    const duration = finiteOptional(draft.durationValue, "Duration", 0);
    const distance = finiteOptional(draft.distanceValue, "Distance", 0);
    if (duration !== null && draft.endedAt.trim()) {
      throw new Error("Choose a reported duration or an end time, not both.");
    }
    const endedAt = intervalEnd(draft, time, "End time");
    return {
      domain,
      time,
      ended_at: endedAt,
      payload: {
        kind: "workout",
        label,
        duration:
          duration === null
            ? null
            : { value: duration, unit: draft.durationUnit },
        distance:
          distance === null
            ? null
            : { value: distance, unit: draft.distanceUnit },
      },
      notes,
    };
  }

  if (domain === "sleep") {
    const endedAt = intervalEnd(draft, time, "End time");
    const quality = finiteOptional(draft.quality, "Sleep quality", 1);
    if (quality !== null && (!Number.isInteger(quality) || quality > 5)) {
      throw new Error("Sleep quality must be a whole number from 1 to 5.");
    }
    return {
      domain,
      time,
      ended_at: endedAt,
      payload: { kind: "sleep", label: label || "Sleep", quality },
      notes,
    };
  }

  if (domain === "symptoms") {
    return {
      domain,
      time,
      ended_at: intervalEnd(draft, time, "End time"),
      payload: { kind: "symptom", label },
      notes,
    };
  }
  throw new Error("Choose a daily entry type.");
}

function buildObservation(
  domain: "measurements" | "symptoms",
  metric: MeasurementMetric | "symptom_severity",
  valueText: string,
  unit: DailyDraft["measurementUnit"] | "score",
  draft: DailyDraft,
  includeIntervalEnd = true,
): ObservationRecord {
  const time = timePoint(draft);
  const end = includeIntervalEnd
    ? intervalEnd(draft, time, "Interval end")
    : null;
  const value = finiteOptional(
    valueText,
    "Value",
    metric === "temperature" ? -Infinity : 0,
  );
  if (value === null)
    throw new Error("Enter a value; an empty value stays unknown.");
  if (
    metric === "symptom_severity" &&
    (!Number.isInteger(value) || value > 10)
  ) {
    throw new Error("Severity must be a whole number from 0 to 10.");
  }
  if (draft.notes.length > 2000)
    throw new Error("Notes can be at most 2,000 characters.");
  if (metric === "symptom_severity") {
    return {
      domain,
      time,
      interval_end: end,
      payload: { value: { metric, value, unit: "score" } },
      notes: draft.notes.trim() || null,
    };
  }
  return {
    domain,
    time,
    interval_end: end,
    payload: {
      value: {
        metric: metric as Exclude<MeasurementMetric, "blood_pressure">,
        value,
        unit: unit as DailyDraft["measurementUnit"],
      },
    },
    notes: draft.notes.trim() || null,
  };
}

export function buildDailyCreateRequest(
  domain: DailyDomain,
  draft: DailyDraft,
  ids: { event: string; observation: string; secondObservation: string },
): BuildResult<DailyCreateRequest> {
  try {
    const events: components["schemas"]["DailyEventCreateRequest"][] = [];
    const observations: components["schemas"]["DailyObservationCreateRequest"][] =
      [];
    const links: components["schemas"]["DailyLinkRequest"][] = [];
    if (domain === "measurements") {
      if (draft.measurementMetric === "blood_pressure") {
        const systolic = buildObservation(
          domain,
          "systolic_pressure",
          draft.systolicValue,
          "mmHg",
          draft,
        );
        const diastolic = buildObservation(
          domain,
          "diastolic_pressure",
          draft.diastolicValue,
          "mmHg",
          draft,
        );
        observations.push(
          {
            id: ids.observation,
            observation: systolic,
            ai_use_allowed: draft.aiUseAllowed,
          },
          {
            id: ids.secondObservation,
            observation: diastolic,
            ai_use_allowed: draft.aiUseAllowed,
          },
        );
      } else {
        const observation = buildObservation(
          domain,
          draft.measurementMetric,
          draft.measurementValue,
          draft.measurementUnit,
          draft,
        );
        observations.push({
          id: ids.observation,
          observation,
          ai_use_allowed: draft.aiUseAllowed,
        });
      }
    } else {
      const event = buildEvent(domain, draft);
      events.push({ id: ids.event, event, ai_use_allowed: draft.aiUseAllowed });
      if (domain === "symptoms" && draft.severity.trim()) {
        const severity = buildObservation(
          "symptoms",
          "symptom_severity",
          draft.severity,
          "score",
          { ...draft, notes: "" },
          false,
        );
        observations.push({
          id: ids.observation,
          observation: severity,
          ai_use_allowed: draft.aiUseAllowed,
        });
        links.push({
          event_id: ids.event,
          observation_id: ids.observation,
          role: "symptom_severity",
        });
      }
    }
    return { ok: true, value: { events, observations, links } };
  } catch (error) {
    return {
      ok: false,
      error:
        error instanceof Error
          ? error.message
          : "Check the daily entry fields and try again.",
    };
  }
}

export function buildDailyUpdateRecord(
  item: DailyItem,
  draft: DailyDraft,
): BuildResult<EventRecord | ObservationRecord> {
  try {
    if (item.object_type === "event") {
      if (item.event.payload.kind === "symptom" && draft.severity.trim()) {
        // A linked symptom keeps its event record separate from the severity Observation.
      }
      return { ok: true, value: buildEvent(item.domain, draft) };
    }
    const metric = item.observation.payload.value.metric;
    if (metric === "custom") {
      return {
        ok: false,
        error:
          "Custom tracker entries use their saved schema and cannot be edited with the standard daily form.",
      };
    }
    if (metric === "symptom_severity") {
      return {
        ok: true,
        value: buildObservation(
          "symptoms",
          metric,
          draft.severity,
          "score",
          draft,
        ),
      };
    }
    return {
      ok: true,
      value: buildObservation(
        "measurements",
        metric,
        draft.measurementValue,
        draft.measurementUnit,
        draft,
      ),
    };
  } catch (error) {
    return {
      ok: false,
      error:
        error instanceof Error
          ? error.message
          : "Check the daily entry fields and try again.",
    };
  }
}

function draftTime(
  draft: DailyDraft,
  time: components["schemas"]["DailyTimePoint"],
): void {
  if (time.precision === "date_only") {
    draft.precision = "date_only";
    draft.localDate = time.local_date;
  } else {
    draft.precision = "instant";
    draft.instant = time.occurred_at;
  }
  draft.timezone = time.timezone;
}

export function draftFromDailyItem(item: DailyItem): DailyDraft {
  const draft = emptyDailyDraft(new Date(item.recorded_at));
  draft.notes = item.notes ?? "";
  draft.aiUseAllowed = item.permissions.ai_use_allowed;
  if (item.object_type === "event") {
    draftTime(draft, item.event.time);
    draft.endedAt = item.event.ended_at ?? "";
    if (item.event.payload.kind === "meal") {
      draft.label = item.event.payload.label;
      draft.foods = item.event.payload.foods?.join(", ") ?? "";
      draft.energyValue = item.event.payload.energy
        ? String(item.event.payload.energy.value)
        : "";
      draft.energyUnit = item.event.payload.energy?.unit ?? "kcal";
    } else if (item.event.payload.kind === "workout") {
      draft.label = item.event.payload.label;
      draft.durationValue = item.event.payload.duration
        ? String(item.event.payload.duration.value)
        : "";
      draft.durationUnit = item.event.payload.duration?.unit ?? "min";
      draft.distanceValue = item.event.payload.distance
        ? String(item.event.payload.distance.value)
        : "";
      draft.distanceUnit = item.event.payload.distance?.unit ?? "km";
      if (item.event.ended_at) draft.durationValue = "";
    } else if (item.event.payload.kind === "sleep") {
      draft.label = item.event.payload.label ?? "Sleep";
      draft.quality = item.event.payload.quality
        ? String(item.event.payload.quality)
        : "";
    } else {
      draft.label = item.event.payload.label;
    }
  } else {
    draftTime(draft, item.observation.time);
    draft.endedAt = item.observation.interval_end ?? "";
    const value = item.observation.payload.value;
    if (value.metric === "custom") {
      draft.label = "Custom tracker entry";
    } else if (value.metric === "symptom_severity") {
      draft.severity = String(value.value);
    } else {
      draft.measurementMetric = value.metric;
      draft.measurementValue = String(value.value);
      draft.measurementUnit = value.unit as DailyDraft["measurementUnit"];
    }
  }
  return draft;
}

export function metricLabel(
  metric: components["schemas"]["MetricKey"],
): string {
  const labels: Record<components["schemas"]["MetricKey"], string> = {
    energy: "Energy",
    duration: "Duration",
    distance: "Distance",
    weight: "Weight",
    temperature: "Temperature",
    systolic_pressure: "Systolic pressure",
    diastolic_pressure: "Diastolic pressure",
    pulse: "Pulse",
    symptom_severity: "Symptom severity",
    symptom_episode_count: "Symptom episodes",
  };
  return labels[metric];
}

export function summaryPresentation(
  summary: components["schemas"]["MetricSummaryV1"],
): { value: string; coverage: string } {
  let value: string;
  if (summary.known_value === null) {
    value = summary.logged_count === 0 ? "Not logged" : "No value recorded";
  } else {
    const number = Number.isInteger(summary.known_value)
      ? String(summary.known_value)
      : String(Number(summary.known_value.toFixed(2)));
    value = `${number} ${summary.unit}`;
  }
  const coverage =
    summary.logged_count === 0
      ? "No entries"
      : `${summary.coverage.known_count} known of ${summary.coverage.total_count} logged${summary.partial ? " · partial" : ""}`;
  return { value, coverage };
}

export function itemTitle(item: DailyItem): string {
  if (item.object_type === "event") return item.event.payload.label ?? "Sleep";
  const value = item.observation.payload.value;
  return value.metric === "custom"
    ? "Custom tracker entry"
    : metricLabel(value.metric);
}

export function itemTimeLabel(item: DailyItem, timezone: string): string {
  const record = item.object_type === "event" ? item.event : item.observation;
  if (record.time.precision === "date_only")
    return `${record.time.local_date} · date only`;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: timezone,
  }).format(new Date(record.time.occurred_at));
}

export function itemValue(
  item: DailyItem,
  customFieldLabels: Record<string, string> = {},
): string {
  if (item.object_type === "event") {
    const payload = item.event.payload;
    if (payload.kind === "meal") {
      return payload.energy
        ? `${payload.energy.value} ${payload.energy.unit}`
        : "Energy not entered";
    }
    if (payload.kind === "workout") {
      if (item.event.ended_at) return `Until ${item.event.ended_at}`;
      if (payload.duration)
        return `${payload.duration.value} ${payload.duration.unit}`;
      return "Duration not entered";
    }
    if (payload.kind === "sleep")
      return item.event.ended_at
        ? `Until ${item.event.ended_at}`
        : "End time unknown";
    return item.linked_observation_ids.length
      ? "Symptom episode · severity recorded"
      : "Symptom episode";
  }
  const value = item.observation.payload.value;
  if (value.metric === "custom") {
    const entries = Object.entries(value.values).map(
      ([fieldId, fieldValue]) =>
        `${customFieldLabels[fieldId] ?? fieldId}: ${formatTrackerValue(fieldValue)}`,
    );
    return entries.length ? entries.join(" · ") : "No tracker values recorded";
  }
  return `${value.value} ${value.unit}`;
}

function formatTrackerValue(value: unknown): string {
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "string" || typeof value === "number")
    return String(value);
  if (
    value &&
    typeof value === "object" &&
    "value" in value &&
    "unit" in value
  ) {
    const quantity = value as { value: unknown; unit: unknown };
    return `${String(quantity.value)} ${String(quantity.unit)}`;
  }
  return "Unknown";
}

export function customTrackerValue(item: DailyItem): CustomTrackerValue | null {
  if (item.object_type !== "observation") return null;
  const value = item.observation.payload.value;
  return value.metric === "custom" ? value : null;
}
