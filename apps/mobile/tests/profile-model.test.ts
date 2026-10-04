import { describe, expect, it } from "vitest";

import {
  buildProfileFields,
  draftFromProfile,
  EMPTY_PROFILE_DRAFT,
  formatProfileValue,
  type ProfileDraft,
  type ProfileItem,
} from "../src/features/profile/model";

function draft(overrides: Partial<ProfileDraft> = {}): ProfileDraft {
  return {
    ...EMPTY_PROFILE_DRAFT,
    kind: "fact",
    key: "has_allergy",
    label: "Has an allergy",
    ...overrides,
  };
}

describe("Profile mobile model", () => {
  it("preserves unknown, false, zero, empty text, and empty list distinctly", () => {
    const unknownValue = buildProfileFields(draft());
    const falseValue = buildProfileFields(
      draft({ value: { type: "boolean", value: false } }),
    );
    const zeroValue = buildProfileFields(
      draft({ value: { type: "number", value: "0" } }),
    );
    const emptyText = buildProfileFields(
      draft({ value: { type: "text", value: "" } }),
    );
    const emptyList = buildProfileFields(
      draft({ value: { type: "text_list", value: "\n  \n" } }),
    );
    expect(unknownValue.ok && unknownValue.fields.profile.value).toBeNull();
    expect(falseValue.ok && falseValue.fields.profile.value).toEqual({
      type: "boolean",
      value: false,
    });
    expect(zeroValue.ok && zeroValue.fields.profile.value).toEqual({
      type: "number",
      value: 0,
    });
    expect(emptyText.ok && emptyText.fields.profile.value).toEqual({
      type: "text",
      value: "",
    });
    expect(emptyList.ok && emptyList.fields.profile.value).toEqual({
      type: "text_list",
      value: [],
    });
    expect(formatProfileValue(null)).toBe("Unknown / not provided");
    expect(formatProfileValue({ type: "boolean", value: false })).toBe("No");
    expect(formatProfileValue({ type: "number", value: 0 })).toBe("0");
  });

  it("requires explicit quantity units and timezone-aware, ordered validity bounds", () => {
    expect(
      buildProfileFields(
        draft({ value: { type: "quantity", value: "0", unit: "" } }),
      ),
    ).toMatchObject({ ok: false });
    expect(
      buildProfileFields(draft({ valid_from: "2026-10-03T12:00:00" })),
    ).toMatchObject({ ok: false });
    expect(
      buildProfileFields(
        draft({
          valid_from: "2026-10-04T12:00:00Z",
          valid_to: "2026-10-03T12:00:00Z",
        }),
      ),
    ).toMatchObject({ ok: false });
    const valid = buildProfileFields(
      draft({
        value: { type: "quantity", value: "0", unit: "kg" },
        valid_from: "2026-10-03T12:00:00-07:00",
        valid_to: "2026-10-04T12:00:00Z",
        ai_use_allowed: false,
        cross_domain_use_allowed: false,
      }),
    );
    expect(valid.ok && valid.fields).toMatchObject({
      profile: { value: { type: "quantity", value: 0, unit: "kg" } },
      valid_from: "2026-10-03T19:00:00.000Z",
      valid_to: "2026-10-04T12:00:00.000Z",
      ai_use_allowed: false,
      cross_domain_use_allowed: false,
    });
  });

  it("loads edit drafts without losing provenance, revision-scoped validity, notes, or permissions", () => {
    const item = {
      id: "00000000-0000-0000-0000-000000000001",
      object_type: "profile_item",
      domain: "profile",
      status: "active",
      title: "Has an allergy",
      valid_from: "2026-10-03T12:00:00Z",
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
      revision: 4,
      notes: "Only if asked",
      metadata: {},
      permissions: { ai_use_allowed: true, cross_domain_use_allowed: false },
      profile: {
        kind: "fact",
        category: "background",
        key: "has_allergy",
        label: "Has an allergy",
        value: { type: "boolean", value: false },
      },
    } satisfies ProfileItem;
    expect(draftFromProfile(item)).toMatchObject({
      key: "has_allergy",
      valid_from: "2026-10-03T12:00:00Z",
      valid_to: "",
      notes: "Only if asked",
      ai_use_allowed: true,
      cross_domain_use_allowed: false,
      value: { type: "boolean", value: false },
    });
    expect(item.revision).toBe(4);
    expect(item.source.kind).toBe("manual");
  });
});
