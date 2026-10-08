import {
  useCallback,
  useLayoutEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from "react";
import { useFocusEffect } from "expo-router";
import type { components } from "@personal-health/api-client";
import { ApiError } from "@personal-health/api-client";

import {
  assistantApi,
  editableProposalCommands,
  listActionProposals,
  mergeProposalSummaries,
} from "./api";
import {
  canAcceptPreviewResponse,
  canAcceptSearchResponse,
  initialProposalEditorState,
  isOlderProposal,
  mergeAssistantSearchPage,
  proposalApplyIdempotencyKey,
  proposalDetailCanReplace,
  proposalEditorReducer,
  replaceProposalSummary,
} from "./state";
import type { ResourceType, TaskKind } from "./state";

function requestMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return (
      error.body?.message ?? "The Assistant request could not be completed."
    );
  }
  return "Could not reach your Health API. Check the connection and try again.";
}

export function useAssistantController() {
  const [status, setStatus] = useState<
    components["schemas"]["AssistantStatusResponse"] | null
  >(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [resourceTypes, setResourceTypes] = useState<ResourceType[]>([]);
  const [domains, setDomains] = useState<string[]>([]);
  const [excludedObjectIds, setExcludedObjectIds] = useState<string[]>([]);
  const [task, setTask] = useState("");
  const [taskKind, setTaskKind] = useState<TaskKind>("general_wellness");
  const [lookbackDays, setLookbackDays] = useState<7 | 30 | 90>(30);
  const [message, setMessage] = useState("");
  const [pack, setPack] = useState<
    components["schemas"]["AIContextPack"] | null
  >(null);
  const [previewKey, setPreviewKey] = useState<string | null>(null);
  const [reply, setReply] = useState<
    components["schemas"]["AssistantMessageResponse"] | null
  >(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [searchText, setSearchText] = useState("");
  const [searchResults, setSearchResults] = useState<
    components["schemas"]["AISearchResult"][]
  >([]);
  const [searchResultKey, setSearchResultKey] = useState<string | null>(null);
  const [searchCursor, setSearchCursor] = useState<string | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searchErrorKey, setSearchErrorKey] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [proposals, setProposals] = useState<
    components["schemas"]["ProposalSummary"][]
  >([]);
  const [proposalDetails, setProposalDetails] = useState<
    Record<string, components["schemas"]["ProposalState"]>
  >({});
  const [proposalsLoading, setProposalsLoading] = useState(true);
  const [proposalError, setProposalError] = useState<string | null>(null);
  const [proposalActionId, setProposalActionId] = useState<string | null>(null);
  const [proposalEditor, dispatchProposalEditor] = useReducer(
    proposalEditorReducer,
    initialProposalEditorState,
  );
  const editingProposalId = proposalEditor.proposalId;
  const editingBaseline =
    proposalEditor.proposalId && proposalEditor.baselineRevision !== null
      ? {
          proposalId: proposalEditor.proposalId,
          revision: proposalEditor.baselineRevision,
        }
      : null;
  const proposalRationaleDraft = proposalEditor.rationale;
  const proposalCommandDraft = proposalEditor.commands;
  const proposalEvidenceDraft = proposalEditor.evidence;
  const [proposalStateFilter, setProposalStateFilter] = useState<
    "pending" | "applied" | "rejected" | "expired" | "superseded"
  >("pending");
  const [proposalCursor, setProposalCursor] = useState<string | null>(null);
  const [proposalHasMore, setProposalHasMore] = useState(false);
  const viewGeneration = useRef(0);
  const proposalDataGeneration = useRef(0);
  const searchGeneration = useRef(0);
  const [searchStale, setSearchStale] = useState(false);

  const scopeTask =
    task.trim() ||
    message.trim().slice(0, 300) ||
    "Review my selected health data";
  const scope = useMemo<components["schemas"]["AIContextRequest"]>(
    () => ({
      task: scopeTask.slice(0, 300),
      task_kind: taskKind,
      resource_types: resourceTypes,
      lookback_days: lookbackDays,
      domains,
      excluded_object_ids: excludedObjectIds,
      sections: ["entries", "today_summaries"],
    }),
    [
      domains,
      excludedObjectIds,
      lookbackDays,
      resourceTypes,
      scopeTask,
      taskKind,
    ],
  );
  const currentScopeKey = JSON.stringify(scope);
  const currentScopeKeyRef = useRef(currentScopeKey);
  useLayoutEffect(() => {
    currentScopeKeyRef.current = currentScopeKey;
  }, [currentScopeKey]);
  const previewIsCurrent = previewKey === currentScopeKey;
  const currentSearchKey = JSON.stringify([searchText.trim(), resourceTypes]);
  const currentSearchKeyRef = useRef(currentSearchKey);
  const visibleSearchResults =
    searchResultKey === currentSearchKey ? searchResults : [];
  const visibleSearchCursor =
    searchResultKey === currentSearchKey ? searchCursor : null;

  const loadStatus = useCallback(async () => {
    try {
      setStatusError(null);
      setStatus(await assistantApi.getAssistantStatus());
    } catch (error) {
      setStatusError(requestMessage(error));
    }
  }, []);

  const loadProposals = useCallback(
    async (append = false, filter = proposalStateFilter) => {
      const generation = viewGeneration.current;
      const dataGeneration = proposalDataGeneration.current;
      try {
        setProposalsLoading(true);
        setProposalError(null);
        const result = await listActionProposals(
          filter,
          append ? (proposalCursor ?? undefined) : undefined,
        );
        if (
          viewGeneration.current === generation &&
          proposalDataGeneration.current === dataGeneration
        ) {
          setProposals((current) => {
            return mergeProposalSummaries(append ? current : [], result.items);
          });
          setProposalCursor(result.next_cursor);
          setProposalHasMore(result.next_cursor !== null);
        }
      } catch (error) {
        if (
          viewGeneration.current === generation &&
          proposalDataGeneration.current === dataGeneration
        )
          setProposalError(requestMessage(error));
      } finally {
        if (
          viewGeneration.current === generation &&
          proposalDataGeneration.current === dataGeneration
        )
          setProposalsLoading(false);
      }
    },
    [proposalCursor, proposalStateFilter],
  );

  useFocusEffect(
    useCallback(() => {
      viewGeneration.current += 1;
      searchGeneration.current += 1;
      setPreviewKey(null);
      setSearchStale(true);
      const generation = viewGeneration.current;
      void loadStatus();
      setProposalCursor(null);
      setProposalHasMore(false);
      void loadProposals(false);
      return () => {
        if (viewGeneration.current === generation) viewGeneration.current += 1;
        searchGeneration.current += 1;
        setPreviewKey(null);
        setSearchStale(true);
      };
    }, [loadProposals, loadStatus]),
  );

  function toggleResourceType(resourceType: ResourceType, enabled: boolean) {
    const next = enabled
      ? [...resourceTypes, resourceType]
      : resourceTypes.filter((value) => value !== resourceType);
    currentSearchKeyRef.current = JSON.stringify([searchText.trim(), next]);
    searchGeneration.current += 1;
    setResourceTypes(next);
    setReply(null);
  }

  function changeSearchText(value: string) {
    currentSearchKeyRef.current = JSON.stringify([value.trim(), resourceTypes]);
    searchGeneration.current += 1;
    setSearchText(value);
  }

  async function previewContext() {
    if (resourceTypes.length === 0) {
      setPreviewError(
        "Choose at least one type of health information to preview.",
      );
      return;
    }
    setBusy(true);
    const generation = viewGeneration.current;
    const previewScopeKey = currentScopeKey;
    setPreviewError(null);
    setReply(null);
    try {
      const result = await assistantApi.previewAIContext(scope);
      if (
        canAcceptPreviewResponse({
          currentGeneration: viewGeneration.current,
          requestGeneration: generation,
          currentScopeKey: currentScopeKeyRef.current,
          requestScopeKey: previewScopeKey,
        })
      ) {
        setPack(result);
        setPreviewKey(previewScopeKey);
      }
    } catch (error) {
      if (
        canAcceptPreviewResponse({
          currentGeneration: viewGeneration.current,
          requestGeneration: generation,
          currentScopeKey: currentScopeKeyRef.current,
          requestScopeKey: previewScopeKey,
        })
      ) {
        setPreviewError(requestMessage(error));
      }
    } finally {
      if (viewGeneration.current === generation) setBusy(false);
    }
  }

  async function search(append = false) {
    if (!searchText.trim()) {
      setSearchError("Enter a word or phrase to search.");
      return;
    }
    if (resourceTypes.length === 0) {
      setSearchError("Choose at least one health item type to search.");
      return;
    }
    const generation = ++searchGeneration.current;
    const queryKey = currentSearchKey;
    setBusy(true);
    setSearchError(null);
    try {
      const result = await assistantApi.searchAIEligibleHealthData({
        q: searchText.trim(),
        types: resourceTypes.join(","),
        limit: 20,
        cursor: append ? searchCursor : undefined,
      });
      if (
        canAcceptSearchResponse({
          currentGeneration: searchGeneration.current,
          requestGeneration: generation,
          currentQueryKey: currentSearchKeyRef.current,
          requestQueryKey: queryKey,
        })
      ) {
        setSearchResults((current) => {
          return mergeAssistantSearchPage({
            current,
            currentKey: searchResultKey,
            incoming: result.items,
            incomingKey: queryKey,
            append,
          });
        });
        setSearchResultKey(queryKey);
        setSearchCursor(result.next_cursor);
        setSearchStale(false);
      }
    } catch (error) {
      if (searchGeneration.current === generation) {
        setSearchError(requestMessage(error));
        setSearchErrorKey(queryKey);
        setSearchStale(true);
      }
    } finally {
      if (searchGeneration.current === generation) setBusy(false);
    }
  }

  async function sendMessage() {
    if (!status?.enabled || !message.trim() || resourceTypes.length === 0)
      return;
    setBusy(true);
    const generation = viewGeneration.current;
    setPreviewError(null);
    setReply(null);
    try {
      const result = await assistantApi.sendAssistantMessage({
        message: message.trim(),
        scope,
      });
      if (viewGeneration.current === generation) setReply(result);
    } catch (error) {
      if (viewGeneration.current === generation) {
        setPreviewError(requestMessage(error));
      }
    } finally {
      if (viewGeneration.current === generation) setBusy(false);
    }
  }

  function replaceProposal(updated: components["schemas"]["ProposalState"]) {
    proposalDataGeneration.current += 1;
    setProposalDetails((current) => {
      const previous = current[updated.id];
      return previous && isOlderProposal(previous, updated)
        ? current
        : { ...current, [updated.id]: updated };
    });
    setProposals((current) =>
      replaceProposalSummary(
        current,
        updated,
        proposalStateFilter === "pending",
      ),
    );
  }

  async function loadProposalDetail(proposalId: string) {
    const dataGeneration = proposalDataGeneration.current;
    const view = viewGeneration.current;
    setProposalActionId(proposalId);
    try {
      const detail = await assistantApi.getActionProposal({
        proposal_id: proposalId,
      });
      if (
        proposalDataGeneration.current !== dataGeneration ||
        viewGeneration.current !== view
      )
        return;
      const summary = proposals.find((item) => item.id === proposalId);
      if (summary && !proposalDetailCanReplace(undefined, detail, summary))
        return;
      setProposalDetails((current) => {
        const previous = current[proposalId];
        return proposalDetailCanReplace(previous, detail, summary)
          ? { ...current, [proposalId]: detail }
          : current;
      });
    } catch (error) {
      setProposalError(requestMessage(error));
    } finally {
      setProposalActionId(null);
    }
  }

  async function refreshProposal(proposalId: string) {
    const current = await assistantApi.getActionProposal({
      proposal_id: proposalId,
    });
    replaceProposal(current);
    return current;
  }

  async function confirmProposal(
    proposal: components["schemas"]["ProposalState"],
  ) {
    if (proposalActionId) return;
    setProposalActionId(proposal.id);
    setProposalError(null);
    try {
      const result = await assistantApi.applyActionProposal(
        { proposal_id: proposal.id },
        {
          proposal_revision: proposal.revision,
          content_hash: proposal.content_hash,
          idempotency_key: proposalApplyIdempotencyKey(
            proposal.id,
            proposal.revision,
          ),
          confirmation: "explicit_user_save",
        },
      );
      replaceProposal(result.proposal);
    } catch (error) {
      try {
        const current = await refreshProposal(proposal.id);
        if (current.state === "applied") {
          setProposalError(
            "This proposal was saved. Its result is shown below.",
          );
        } else if (error instanceof ApiError && error.status === 409) {
          setProposalError(
            current.last_validation_summary?.valid === false
              ? "A referenced record changed. Current record details are shown below; edit its evidence or target revisions and save a new proposal revision before confirming again."
              : "The proposal changed after this card was loaded. Review the latest proposal revision before confirming again.",
          );
        } else if (error instanceof ApiError && error.status === 410) {
          setProposalError(
            "This proposal has expired and cannot be confirmed.",
          );
        } else {
          setProposalError(
            `${requestMessage(error)} If the connection failed during confirmation, retrying uses the same receipt key.`,
          );
        }
      } catch {
        setProposalError(
          `${requestMessage(error)} The outcome is unknown; retry this same proposal to check or replay the saved result.`,
        );
      }
    } finally {
      setProposalActionId(null);
    }
  }

  async function rejectProposal(
    proposal: components["schemas"]["ProposalState"],
  ) {
    if (proposalActionId) return;
    setProposalActionId(proposal.id);
    setProposalError(null);
    try {
      const result = await assistantApi.rejectActionProposal(
        { proposal_id: proposal.id },
        { proposal_revision: proposal.revision },
      );
      replaceProposal(result);
      if (editingProposalId === proposal.id) {
        dispatchProposalEditor({ type: "clear" });
      }
    } catch (error) {
      setProposalError(requestMessage(error));
    } finally {
      setProposalActionId(null);
    }
  }

  function beginEdit(proposal: components["schemas"]["ProposalState"]) {
    dispatchProposalEditor({
      type: "begin",
      proposalId: proposal.id,
      revision: proposal.revision,
      rationale: proposal.rationale,
      commands: editableProposalCommands(proposal.commands),
      evidence: JSON.stringify(
        proposal.evidence_refs.map(({ object_id, revision }) => ({
          object_id,
          revision,
        })),
        null,
        2,
      ),
    });
    setProposalError(null);
  }

  async function saveProposalEdit(
    proposal: components["schemas"]["ProposalState"],
  ) {
    if (proposalActionId) return;
    if (!editingBaseline || editingBaseline.proposalId !== proposal.id) {
      setProposalError(
        "Reopen this proposal before saving so its review baseline is explicit.",
      );
      return;
    }
    let commands: components["schemas"]["ProposalDraftCommand"][];
    let evidenceRefs: { object_id: string; revision: number }[];
    try {
      const parsed: unknown = JSON.parse(proposalCommandDraft);
      if (!Array.isArray(parsed) || parsed.length === 0 || parsed.length > 10)
        throw new Error("Enter between one and ten typed commands.");
      commands = parsed as components["schemas"]["ProposalDraftCommand"][];
      const parsedEvidence: unknown = JSON.parse(proposalEvidenceDraft);
      if (!Array.isArray(parsedEvidence) || parsedEvidence.length > 20)
        throw new Error("Enter zero to twenty evidence references.");
      evidenceRefs = parsedEvidence as {
        object_id: string;
        revision: number;
      }[];
    } catch (error) {
      setProposalError(
        error instanceof Error
          ? `Command edits are not valid JSON: ${error.message}`
          : "Command edits are not valid JSON.",
      );
      return;
    }
    setProposalActionId(proposal.id);
    setProposalError(null);
    try {
      const updated = await assistantApi.editActionProposal(
        { proposal_id: proposal.id },
        {
          expected_revision: editingBaseline.revision,
          rationale: proposalRationaleDraft,
          evidence_refs: evidenceRefs,
          commands,
        },
      );
      replaceProposal(updated);
      dispatchProposalEditor({ type: "clear" });
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        let latestRevision: number | null = null;
        try {
          latestRevision = (await refreshProposal(proposal.id)).revision;
        } catch {
          // Keep the submitted draft and baseline available for a later retry.
        }
        dispatchProposalEditor({
          type: "conflict",
          proposalId: proposal.id,
          latestRevision,
        });
        setProposalError(
          "This proposal changed while you were editing. Your draft is preserved against its original revision. Review the latest proposal before deliberately replacing this draft.",
        );
      } else {
        setProposalError(
          `${requestMessage(error)} Your draft is preserved. Refresh and review the latest record before adopting a newer revision.`,
        );
      }
    } finally {
      setProposalActionId(null);
    }
  }

  return {
    status,
    statusError,
    resourceTypes,
    domains,
    excludedObjectIds,
    task,
    taskKind,
    lookbackDays,
    message,
    pack,
    previewIsCurrent,
    reply,
    previewError,
    searchText,
    visibleSearchResults,
    visibleSearchCursor,
    searchError,
    searchErrorKey,
    currentSearchKey,
    busy,
    proposals,
    proposalDetails,
    proposalsLoading,
    proposalError,
    proposalActionId,
    editingProposalId,
    editingBaseline,
    proposalRationaleDraft,
    proposalCommandDraft,
    proposalEvidenceDraft,
    proposalStateFilter,
    proposalCursor,
    proposalHasMore,
    searchStale,
    setDomains,
    setExcludedObjectIds,
    setTask,
    setTaskKind,
    setLookbackDays,
    setMessage,
    setProposalStateFilter,
    setProposalCursor,
    setProposalHasMore,
    setProposals,
    setProposalDetails,
    loadStatus,
    loadProposals,
    toggleResourceType,
    changeSearchText,
    previewContext,
    search,
    sendMessage,
    loadProposalDetail,
    confirmProposal,
    rejectProposal,
    beginEdit,
    saveProposalEdit,
    cancelProposalEdit: () => dispatchProposalEditor({ type: "clear" }),
    changeProposalRationale: (value: string) =>
      dispatchProposalEditor({ type: "rationale_changed", value }),
    changeProposalCommands: (value: string) =>
      dispatchProposalEditor({ type: "commands_changed", value }),
    changeProposalEvidence: (value: string) =>
      dispatchProposalEditor({ type: "evidence_changed", value }),
  };
}
