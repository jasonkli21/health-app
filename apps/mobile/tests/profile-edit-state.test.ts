import { describe, expect, it } from "vitest";

import {
  acceptProfileRefresh,
  EMPTY_PROFILE_EDIT_STATE,
  recordProfileDraft,
} from "../src/features/profile/editState";
import type { ProfileDraft, ProfileItem } from "../src/features/profile/model";

function item(revision: number, label: string): ProfileItem {
  return {
    id: "00000000-0000-0000-0000-000000000001",
    object_type: "profile_item",
    domain: "profile",
    status: "active",
    title: label,
    valid_from: null,
    valid_to: null,
    recorded_at: "2026-10-03T12:00:00Z",
    created_at: "2026-10-03T12:00:00Z",
    updated_at: "2026-10-03T12:00:00Z",
    source: {
      id: "00000000-0000-0000-0000-000000000002",
      kind: "manual",
      name: "You",
    },
    confirmation_status: "user_confirmed",
    schema_version: 1,
    revision,
    notes: null,
    metadata: {},
    permissions: { ai_use_allowed: false, cross_domain_use_allowed: false },
    profile: {
      kind: "fact",
      category: "background",
      key: "preferred_name",
      label,
      value: { type: "text", value: "Sam" },
    },
  };
}

function editedDraft(draft: ProfileDraft): ProfileDraft {
  return { ...draft, label: "My unsaved draft" };
}

describe("Profile edit refresh state", () => {
  it("keeps a dirty draft and its revision through background refreshes", () => {
    const initial = acceptProfileRefresh(
      EMPTY_PROFILE_EDIT_STATE,
      item(1, "Preferred name"),
    );
    const dirty = recordProfileDraft(initial, editedDraft(initial.draft!));
    const refreshed = acceptProfileRefresh(dirty, item(2, "Server update"));

    expect(refreshed).toBe(dirty);
    expect(refreshed.item?.revision).toBe(1);
    expect(refreshed.draft?.label).toBe("My unsaved draft");
    expect(refreshed.dirty).toBe(true);
  });

  it("retains a dirty draft when a refresh fails without applying a replacement", () => {
    const initial = acceptProfileRefresh(
      EMPTY_PROFILE_EDIT_STATE,
      item(1, "Preferred name"),
    );
    const dirty = recordProfileDraft(initial, editedDraft(initial.draft!));
    // A failed GET has no incoming item to apply; the screen keeps this state.
    expect(dirty.item?.revision).toBe(1);
    expect(dirty.draft?.label).toBe("My unsaved draft");
  });

  it("replaces draft and revision only after an explicit successful conflict reload", () => {
    const initial = acceptProfileRefresh(
      EMPTY_PROFILE_EDIT_STATE,
      item(1, "Preferred name"),
    );
    const dirty = recordProfileDraft(initial, editedDraft(initial.draft!));
    const reloaded = acceptProfileRefresh(
      dirty,
      item(2, "Server update"),
      true,
    );

    expect(reloaded.item?.revision).toBe(2);
    expect(reloaded.draft?.label).toBe("Server update");
    expect(reloaded.dirty).toBe(false);
    expect(reloaded.formGeneration).toBe(initial.formGeneration + 1);
  });

  it("refreshes a clean draft from the server", () => {
    const initial = acceptProfileRefresh(
      EMPTY_PROFILE_EDIT_STATE,
      item(1, "Preferred name"),
    );
    const refreshed = acceptProfileRefresh(initial, item(2, "Server update"));

    expect(refreshed.item?.revision).toBe(2);
    expect(refreshed.draft?.label).toBe("Server update");
    expect(refreshed.dirty).toBe(false);
  });
});
