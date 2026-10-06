import { describe, expect, it, vi } from "vitest";

import type { components } from "@personal-health/api-client";
import {
  assistantApi,
  editableProposalCommands,
  listActionProposals,
  mergeProposalSummaries,
} from "../src/features/assistant/api";

const proposalId = "00000000-0000-0000-0000-000000000001";
const targetId = "00000000-0000-0000-0000-000000000002";

describe("Assistant proposal review helpers", () => {
  it("keeps omitted Profile fields distinct from explicit null through editing", () => {
    const base: components["schemas"]["ProfileUpdateCommand"] = {
      action: "profile.update",
      object_id: targetId,
      expected_revision: 3,
      profile: {
        kind: "fact",
        category: "background",
        key: "diet",
        label: "Diet",
        value: { type: "text", value: "vegetarian" },
      },
    };
    const explicitClear: components["schemas"]["ProfileUpdateCommand"] = {
      ...base,
      notes: null,
      metadata: null,
      valid_from: null,
      valid_to: null,
    };

    const edited = JSON.parse(
      editableProposalCommands([base, explicitClear]),
    ) as Record<string, unknown>[];

    expect(edited[0]).not.toHaveProperty("notes");
    expect(edited[0]).not.toHaveProperty("metadata");
    expect(edited[0]).not.toHaveProperty("valid_from");
    expect(edited[1]).toMatchObject({
      notes: null,
      metadata: null,
      valid_from: null,
      valid_to: null,
    });
  });

  it("deduplicates proposal pages by ID and keeps the newest summary", () => {
    const first: components["schemas"]["ProposalSummary"] = {
      id: proposalId,
      revision: 1,
      content_hash: "a".repeat(64),
      state: "pending",
      origin: "user",
      rationale: "old",
      created_at: "2026-10-06T12:00:00Z",
      expires_at: "2026-10-07T12:00:00Z",
      updated_at: "2026-10-06T12:00:00Z",
    };
    const latest = { ...first, revision: 2, rationale: "reviewed" };

    expect(mergeProposalSummaries([first], [latest])).toEqual([latest]);
  });

  it("requests the selected state and cursor for proposal pagination", async () => {
    const request = vi
      .spyOn(assistantApi, "listActionProposals")
      .mockResolvedValue({ items: [], next_cursor: "next-page" });

    await listActionProposals("pending", "after-token");

    expect(request).toHaveBeenCalledWith({
      state: "pending",
      limit: 50,
      cursor: "after-token",
    });
    request.mockRestore();
  });
});
