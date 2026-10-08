import { describe, expect, it } from "vitest";
import type { components } from "@personal-health/api-client";
import {
  canAcceptPreviewResponse,
  canAcceptSearchResponse,
  initialProposalEditorState,
  mergeAssistantSearchPage,
  proposalApplyIdempotencyKey,
  proposalDetailCanReplace,
  proposalEditorReducer,
  replaceProposalSummary,
} from "../src/features/assistant/state";

type SearchResult = components["schemas"]["AISearchResult"];
type Proposal = components["schemas"]["ProposalState"];
type ProposalSummary = components["schemas"]["ProposalSummary"];

function searchResult(objectId: string, revision = 1): SearchResult {
  return {
    object_id: objectId,
    revision,
    object_type: "event",
    title: objectId,
    domain: "exercise",
    excerpt: "Walk",
    source_kind: "manual",
    confirmation_status: "user_confirmed",
  };
}

function proposal(
  revision: number,
  updatedAt = "2026-10-08T12:00:00Z",
): Proposal {
  return {
    id: "proposal-1",
    revision,
    content_hash: "a".repeat(64),
    state: "pending",
    origin: "user",
    rationale: "Review this change",
    commands: [],
    evidence_refs: [],
    created_at: "2026-10-08T11:00:00Z",
    updated_at: updatedAt,
    expires_at: "2026-10-09T12:00:00Z",
  };
}

function summary(revision: number): ProposalSummary {
  return {
    id: "proposal-1",
    revision,
    content_hash: "a".repeat(64),
    state: "pending",
    origin: "user",
    rationale: "Review this change",
    created_at: "2026-10-08T11:00:00Z",
    updated_at: "2026-10-08T12:00:00Z",
    expires_at: "2026-10-09T12:00:00Z",
  };
}

describe("Assistant workflow state", () => {
  it("rejects preview responses after scope or focus generation changes", () => {
    expect(
      canAcceptPreviewResponse({
        currentGeneration: 4,
        requestGeneration: 4,
        currentScopeKey: "scope-b",
        requestScopeKey: "scope-a",
      }),
    ).toBe(false);
    expect(
      canAcceptPreviewResponse({
        currentGeneration: 5,
        requestGeneration: 4,
        currentScopeKey: "scope-a",
        requestScopeKey: "scope-a",
      }),
    ).toBe(false);
  });

  it("rejects search responses after query or resource type changes", () => {
    expect(
      canAcceptSearchResponse({
        currentGeneration: 3,
        requestGeneration: 2,
        currentQueryKey: "new-query",
        requestQueryKey: "old-query",
      }),
    ).toBe(false);
  });

  it("merges only pages for the current query and deduplicates object IDs", () => {
    const first = searchResult("event-1", 1);
    const newer = searchResult("event-1", 2);
    const second = searchResult("event-2");
    expect(
      mergeAssistantSearchPage({
        current: [first],
        currentKey: "walking",
        incoming: [newer, second],
        incomingKey: "walking",
        append: true,
      }),
    ).toEqual([newer, second]);
    expect(
      mergeAssistantSearchPage({
        current: [first],
        currentKey: "walking",
        incoming: [second],
        incomingKey: "sleep",
        append: true,
      }),
    ).toEqual([second]);
  });

  it("does not allow an older proposal detail to replace a newer summary", () => {
    expect(proposalDetailCanReplace(undefined, proposal(1), summary(2))).toBe(
      false,
    );
    expect(proposalDetailCanReplace(undefined, proposal(2), summary(2))).toBe(
      true,
    );
  });

  it("removes a successfully applied proposal from the pending list", () => {
    const applied = { ...proposal(3), state: "applied" as const };
    expect(replaceProposalSummary([summary(2)], applied, true)).toEqual([]);
  });

  it("preserves the original baseline and edit draft through a revision conflict", () => {
    const editing = proposalEditorReducer(initialProposalEditorState, {
      type: "begin",
      proposalId: "proposal-1",
      revision: 3,
      rationale: "My rationale draft",
      commands: '[{"action":"profile.update"}]',
      evidence: "[]",
    });
    const changed = proposalEditorReducer(editing, {
      type: "conflict",
      proposalId: "proposal-1",
      latestRevision: 4,
    });

    expect(changed).toMatchObject({
      proposalId: "proposal-1",
      baselineRevision: 3,
      rationale: "My rationale draft",
      commands: '[{"action":"profile.update"}]',
      evidence: "[]",
      conflictRevision: 4,
    });
  });

  it("reuses the same confirmation receipt identity for one proposal revision", () => {
    expect(proposalApplyIdempotencyKey("proposal-1", 7)).toBe(
      proposalApplyIdempotencyKey("proposal-1", 7),
    );
    expect(proposalApplyIdempotencyKey("proposal-1", 7)).not.toBe(
      proposalApplyIdempotencyKey("proposal-1", 8),
    );
  });
});
