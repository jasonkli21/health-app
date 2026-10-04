import { describe, expect, it } from "vitest";

import {
  buildDailyCreateRequest,
  buildDailyUpdateRecord,
  draftFromDailyItem,
  emptyDailyDraft,
  summaryPresentation,
} from "../src/features/daily/model";
import type {
  DailyDraft,
  DailyEvent,
  DailyObservation,
} from "../src/features/daily/model";

const IDS = {
  event: "00000000-0000-0000-0000-000000000001",
  observation: "00000000-0000-0000-0000-000000000002",
  secondObservation: "00000000-0000-0000-0000-000000000003",
};

function draft(patch: Partial<DailyDraft> = {}): DailyDraft {
  return {
    ...emptyDailyDraft(new Date("2026-05-01T16:00:00Z")),
    label: "Entry",
    ...patch,
  };
}

function built(
  domain: "nutrition" | "exercise" | "sleep" | "symptoms" | "measurements",
  value: DailyDraft,
) {
  const result = buildDailyCreateRequest(domain, value, IDS);
  if (!result.ok) throw new Error(result.error);
  return result.value;
}

describe("daily entry builders", () => {
  it("presents not logged, explicit zero, and partial coverage as distinct states", () => {
    const empty = summaryPresentation({
      domain: "nutrition",
      metric: "energy",
      known_value: null,
      unit: "kcal",
      logged_count: 0,
      coverage: { known_count: 0, total_count: 0 },
      method_version: "today-v1/sum-known-v1/unit-v1",
      partial: false,
    });
    const zero = summaryPresentation({
      domain: "nutrition",
      metric: "energy",
      known_value: 0,
      unit: "kcal",
      logged_count: 2,
      coverage: { known_count: 1, total_count: 2 },
      method_version: "today-v1/sum-known-v1/unit-v1",
      partial: true,
    });
    expect(empty).toEqual({ value: "Not logged", coverage: "No entries" });
    expect(zero).toEqual({
      value: "0 kcal",
      coverage: "1 known of 2 logged · partial",
    });
  });

  it("keeps an absent meal energy unknown and an explicit zero as a known quantity", () => {
    const unknown = built(
      "nutrition",
      draft({ label: "Lunch", foods: "Rice, beans" }),
    );
    expect(unknown.events?.[0]?.event.payload).toMatchObject({
      kind: "meal",
      label: "Lunch",
      foods: ["Rice", "beans"],
      energy: null,
    });

    const zero = built(
      "nutrition",
      draft({ label: "Lunch", energyValue: "0", energyUnit: "kJ" }),
    );
    expect(zero.events?.[0]?.event.payload).toMatchObject({
      kind: "meal",
      energy: { value: 0, unit: "kJ" },
    });
  });

  it("creates date-only meal entries without inventing an instant", () => {
    const request = built(
      "nutrition",
      draft({
        label: "Lunch",
        precision: "date_only",
        localDate: "2026-05-01",
      }),
    );
    expect(request.events?.[0]?.event.time).toEqual({
      precision: "date_only",
      local_date: "2026-05-01",
      timezone: "America/Los_Angeles",
    });
  });

  it("keeps workout duration or end-time semantics distinct and units explicit", () => {
    const duration = built(
      "exercise",
      draft({
        label: "Walk",
        durationValue: "30",
        durationUnit: "min",
        distanceValue: "2",
        distanceUnit: "mi",
      }),
    );
    expect(duration.events?.[0]?.event).toMatchObject({
      payload: {
        kind: "workout",
        duration: { value: 30, unit: "min" },
        distance: { value: 2, unit: "mi" },
      },
      ended_at: null,
    });

    const interval = built(
      "exercise",
      draft({
        label: "Walk",
        instant: "2026-05-01T23:30:00-07:00",
        endedAt: "2026-05-02T01:00:00-07:00",
      }),
    );
    expect(interval.events?.[0]?.event.ended_at).toBe(
      "2026-05-02T01:00:00-07:00",
    );
    expect(
      buildDailyCreateRequest(
        "exercise",
        draft({
          label: "Walk",
          durationValue: "30",
          endedAt: "2026-05-01T17:00:00Z",
        }),
        IDS,
      ),
    ).toMatchObject({
      ok: false,
      error: "Choose a reported duration or an end time, not both.",
    });
  });

  it("requires exact start/end time for sleep and validates optional quality", () => {
    const request = built(
      "sleep",
      draft({
        label: "",
        endedAt: "2026-05-02T06:00:00-07:00",
        quality: "4",
      }),
    );
    expect(request.events?.[0]?.event).toMatchObject({
      domain: "sleep",
      ended_at: "2026-05-02T06:00:00-07:00",
      payload: { kind: "sleep", label: "Sleep", quality: 4 },
    });
    expect(
      buildDailyCreateRequest("sleep", draft({ precision: "date_only" }), IDS)
        .ok,
    ).toBe(false);
  });

  it("saves symptom and optional severity as linked records in one bounded request", () => {
    const request = built(
      "symptoms",
      draft({ label: "Headache", severity: "0" }),
    );
    expect(request.events).toHaveLength(1);
    expect(request.observations?.[0]?.observation.payload.value).toEqual({
      metric: "symptom_severity",
      value: 0,
      unit: "score",
    });
    expect(request.links).toEqual([
      {
        event_id: IDS.event,
        observation_id: IDS.observation,
        role: "symptom_severity",
      },
    ]);
    expect(
      built("symptoms", draft({ label: "Headache" })).observations,
    ).toEqual([]);
  });

  it("creates blood pressure as a systolic/diastolic pair with blank values rejected", () => {
    const request = built(
      "measurements",
      draft({
        measurementMetric: "blood_pressure",
        systolicValue: "120",
        diastolicValue: "80",
      }),
    );
    expect(
      request.observations?.map((entry) => entry.observation.payload.value),
    ).toEqual([
      { metric: "systolic_pressure", value: 120, unit: "mmHg" },
      { metric: "diastolic_pressure", value: 80, unit: "mmHg" },
    ]);
    expect(
      buildDailyCreateRequest(
        "measurements",
        draft({ measurementMetric: "blood_pressure", systolicValue: "120" }),
        IDS,
      ).ok,
    ).toBe(false);
  });

  it("validates explicit values, timezone/date syntax, and malformed times", () => {
    expect(
      buildDailyCreateRequest(
        "measurements",
        draft({ measurementValue: "0" }),
        IDS,
      ).ok,
    ).toBe(true);
    expect(
      buildDailyCreateRequest(
        "measurements",
        draft({ measurementValue: "" }),
        IDS,
      ),
    ).toMatchObject({ ok: false });
    expect(
      buildDailyCreateRequest(
        "nutrition",
        draft({ label: "Lunch", energyValue: "-1" }),
        IDS,
      ),
    ).toMatchObject({ ok: false });
    expect(
      buildDailyCreateRequest(
        "nutrition",
        draft({ label: "Lunch", instant: "2026-02-30T12:00:00Z" }),
        IDS,
      ),
    ).toMatchObject({ ok: false });
    expect(
      buildDailyCreateRequest(
        "nutrition",
        draft({ label: "Lunch", timezone: "Not/AZone" }),
        IDS,
      ),
    ).toMatchObject({ ok: false });
    const precise = "2026-05-01T09:00:00.123456-07:00";
    expect(
      built("nutrition", draft({ label: "Lunch", instant: precise }))
        .events?.[0]?.event.time,
    ).toMatchObject({
      precision: "instant",
      occurred_at: precise,
    });
  });

  it("round trips API entries into editable drafts without losing unknown or zero", () => {
    const zeroMeal: DailyEvent = {
      id: IDS.event,
      object_type: "event",
      domain: "nutrition",
      status: "active",
      title: "Lunch",
      valid_from: null,
      valid_to: null,
      recorded_at: "2026-05-01T16:00:00Z",
      created_at: "2026-05-01T16:00:00Z",
      updated_at: "2026-05-01T16:00:00Z",
      source: { id: IDS.observation, kind: "manual", name: "You" },
      confirmation_status: "user_confirmed",
      schema_version: 1,
      revision: 1,
      notes: null,
      metadata: {},
      permissions: { ai_use_allowed: false, cross_domain_use_allowed: false },
      linked_observation_ids: [],
      event: {
        domain: "nutrition",
        time: {
          precision: "date_only",
          local_date: "2026-05-01",
          timezone: "America/Los_Angeles",
        },
        ended_at: null,
        notes: null,
        payload: {
          kind: "meal",
          label: "Lunch",
          foods: [],
          energy: { value: 0, unit: "kcal" },
        },
      },
    };
    const restored = draftFromDailyItem(zeroMeal);
    expect(restored.precision).toBe("date_only");
    expect(restored.energyValue).toBe("0");
    expect(buildDailyUpdateRecord(zeroMeal, restored)).toMatchObject({
      ok: true,
      value: {
        time: { precision: "date_only", local_date: "2026-05-01" },
        payload: { energy: { value: 0, unit: "kcal" } },
      },
    });

    const severity: DailyObservation = {
      id: IDS.observation,
      object_type: "observation",
      domain: "symptoms",
      status: "active",
      title: "Symptom severity",
      valid_from: null,
      valid_to: null,
      recorded_at: "2026-05-01T16:00:00Z",
      created_at: "2026-05-01T16:00:00Z",
      updated_at: "2026-05-01T16:00:00Z",
      source: { id: IDS.event, kind: "manual", name: "You" },
      confirmation_status: "user_confirmed",
      schema_version: 1,
      revision: 1,
      notes: null,
      metadata: {},
      permissions: { ai_use_allowed: false, cross_domain_use_allowed: false },
      observation: {
        domain: "symptoms",
        time: {
          precision: "instant",
          occurred_at: "2026-05-01T16:00:00Z",
          timezone: "America/Los_Angeles",
        },
        interval_end: null,
        notes: null,
        payload: {
          value: { metric: "symptom_severity", value: 0, unit: "score" },
        },
      },
    };
    expect(draftFromDailyItem(severity).severity).toBe("0");
    expect(
      buildDailyUpdateRecord(severity, draftFromDailyItem(severity)),
    ).toMatchObject({
      ok: true,
      value: {
        payload: {
          value: { metric: "symptom_severity", value: 0, unit: "score" },
        },
      },
    });
  });
});
