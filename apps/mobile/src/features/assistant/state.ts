import type { components } from "@personal-health/api-client";

type ProposalSummary = components["schemas"]["ProposalSummary"];
type ProposalState = components["schemas"]["ProposalState"];
type Proposal = ProposalSummary | ProposalState;
type SearchResult = components["schemas"]["AISearchResult"];

export type ResourceType =
  components["schemas"]["AIContextRequest"]["resource_types"][number];
export type TaskKind = NonNullable<
  components["schemas"]["AIContextRequest"]["task_kind"]
>;

export interface ProposalEditorState {
  proposalId: string | null;
  baselineRevision: number | null;
  rationale: string;
  commands: string;
  evidence: string;
  conflictRevision: number | null;
}

export const initialProposalEditorState: ProposalEditorState = {
  proposalId: null,
  baselineRevision: null,
  rationale: "",
  commands: "",
  evidence: "",
  conflictRevision: null,
};

export type ProposalEditorAction =
  | {
      type: "begin";
      proposalId: string;
      revision: number;
      rationale: string;
      commands: string;
      evidence: string;
    }
  | { type: "rationale_changed"; value: string }
  | { type: "commands_changed"; value: string }
  | { type: "evidence_changed"; value: string }
  | { type: "conflict"; proposalId: string; latestRevision: number | null }
  | { type: "clear" };

export function proposalEditorReducer(
  state: ProposalEditorState,
  action: ProposalEditorAction,
): ProposalEditorState {
  switch (action.type) {
    case "begin":
      return {
        proposalId: action.proposalId,
        baselineRevision: action.revision,
        rationale: action.rationale,
        commands: action.commands,
        evidence: action.evidence,
        conflictRevision: null,
      };
    case "rationale_changed":
      return { ...state, rationale: action.value };
    case "commands_changed":
      return { ...state, commands: action.value };
    case "evidence_changed":
      return { ...state, evidence: action.value };
    case "conflict":
      if (state.proposalId !== action.proposalId) return state;
      return {
        ...state,
        conflictRevision: action.latestRevision,
      };
    case "clear":
      return initialProposalEditorState;
  }
}

export function isOlderProposal(
  current: Proposal,
  incoming: Proposal,
): boolean {
  return (
    current.revision > incoming.revision ||
    (current.revision === incoming.revision &&
      Date.parse(current.updated_at) > Date.parse(incoming.updated_at))
  );
}

export function canAcceptAssistantResponse(
  currentGeneration: number,
  requestGeneration: number,
): boolean {
  return currentGeneration === requestGeneration;
}

export function canAcceptPreviewResponse(input: {
  currentGeneration: number;
  requestGeneration: number;
  currentScopeKey: string;
  requestScopeKey: string;
}): boolean {
  return (
    canAcceptAssistantResponse(
      input.currentGeneration,
      input.requestGeneration,
    ) && input.currentScopeKey === input.requestScopeKey
  );
}

export function canAcceptSearchResponse(input: {
  currentGeneration: number;
  requestGeneration: number;
  currentQueryKey: string;
  requestQueryKey: string;
}): boolean {
  return (
    canAcceptAssistantResponse(
      input.currentGeneration,
      input.requestGeneration,
    ) && input.currentQueryKey === input.requestQueryKey
  );
}

export function mergeAssistantSearchPage(input: {
  current: SearchResult[];
  currentKey: string | null;
  incoming: SearchResult[];
  incomingKey: string;
  append: boolean;
}): SearchResult[] {
  const combined =
    input.append && input.currentKey === input.incomingKey
      ? [...input.current, ...input.incoming]
      : input.incoming;
  return [...new Map(combined.map((item) => [item.object_id, item])).values()];
}

export function proposalDetailCanReplace(
  current: ProposalState | undefined,
  incoming: ProposalState,
  summary?: ProposalSummary,
): boolean {
  return (
    (!current || !isOlderProposal(current, incoming)) &&
    (!summary || !isOlderProposal(summary, incoming))
  );
}

export function replaceProposalSummary(
  current: ProposalSummary[],
  updated: ProposalState,
  pendingFilter: boolean,
): ProposalSummary[] {
  const previous = current.find((proposal) => proposal.id === updated.id);
  if (previous && isOlderProposal(previous, updated)) return current;
  if (pendingFilter && updated.state !== "pending") {
    return current.filter((proposal) => proposal.id !== updated.id);
  }
  return current.map((proposal) => {
    if (proposal.id !== updated.id) return proposal;
    if (proposal.revision > updated.revision) return proposal;
    return {
      id: updated.id,
      revision: updated.revision,
      content_hash: updated.content_hash,
      state: updated.state,
      origin: updated.origin,
      rationale: updated.rationale,
      created_at: updated.created_at,
      expires_at: updated.expires_at,
      updated_at: updated.updated_at,
    };
  });
}

export function proposalApplyIdempotencyKey(
  proposalId: string,
  revision: number,
): string {
  return `proposal-${proposalId}-${revision}`;
}
