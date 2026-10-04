import { describe, expect, it } from "vitest";

import {
  acceptDailyRefresh,
  EMPTY_DAILY_EDIT_STATE,
  recordDailyDraft,
} from "../src/features/daily/editState";
import type { DailyEvent } from "../src/features/daily/model";

function item(revision: number, label: string, id = "daily-event"): DailyEvent {
  return {
    id,
    object_type: "event",
    domain: "symptoms",
    status: "active",
    title: label,
    valid_from: null,
    valid_to: null,
    recorded_at: "2026-10-04T12:00:00Z",
    created_at: "2026-10-04T12:00:00Z",
    updated_at: "2026-10-04T12:00:00Z",
    source: { id: "manual-source", kind: "manual", name: "You" },
    confirmation_status: "user_confirmed",
    schema_version: 1,
    revision,
    notes: null,
    metadata: {},
    permissions: { ai_use_allowed: false, cross_domain_use_allowed: false },
    linked_observation_ids: [],
    event: {
      domain: "symptoms",
      time: {
        precision: "instant",
        occurred_at: "2026-10-04T12:00:00.123456Z",
        timezone: "UTC",
      },
      ended_at: null,
      notes: null,
      payload: { kind: "symptom", label },
    },
  };
}

describe("daily edit refresh state", () => {
  it("keeps a dirty form draft and its original revision through focus refreshes", () => {
    const initial = acceptDailyRefresh(
      EMPTY_DAILY_EDIT_STATE,
      item(1, "Headache"),
    );
    const dirty = recordDailyDraft(initial, {
      ...initial.draft!,
      label: "My draft",
    });

    expect(acceptDailyRefresh(dirty, item(2, "Server change"))).toBe(dirty);
    expect(dirty.item?.revision).toBe(1);
    expect(dirty.draft?.label).toBe("My draft");
  });

  it("keeps the draft and revision after a failed refresh", () => {
    const initial = acceptDailyRefresh(
      EMPTY_DAILY_EDIT_STATE,
      item(1, "Headache"),
    );
    const dirty = recordDailyDraft(initial, {
      ...initial.draft!,
      label: "My draft",
    });

    expect(dirty.item?.revision).toBe(1);
    expect(dirty.draft?.label).toBe("My draft");
    expect(dirty.dirty).toBe(true);
  });

  it("replaces draft and revision only after an explicit successful conflict reload", () => {
    const initial = acceptDailyRefresh(
      EMPTY_DAILY_EDIT_STATE,
      item(1, "Headache"),
    );
    const dirty = recordDailyDraft(initial, {
      ...initial.draft!,
      label: "My draft",
    });
    const latest = acceptDailyRefresh(dirty, item(2, "Server change"), true);

    expect(latest.item?.revision).toBe(2);
    expect(latest.draft?.label).toBe("Server change");
    expect(latest.dirty).toBe(false);
    expect(latest.formGeneration).toBe(initial.formGeneration + 1);
  });

  it("does not apply a refresh from another route item to the current draft", () => {
    const initial = acceptDailyRefresh(
      EMPTY_DAILY_EDIT_STATE,
      item(1, "Headache"),
    );
    const dirty = recordDailyDraft(initial, {
      ...initial.draft!,
      label: "My draft",
    });
    const changedRoute = acceptDailyRefresh(
      dirty,
      item(1, "Nausea", "other-item"),
    );

    expect(changedRoute.item?.id).toBe("other-item");
    expect(changedRoute.draft?.label).toBe("Nausea");
    expect(changedRoute.dirty).toBe(false);
  });
});
