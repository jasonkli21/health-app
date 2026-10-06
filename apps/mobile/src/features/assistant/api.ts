import { HealthApiClient } from "@personal-health/api-client";
import type { components } from "@personal-health/api-client";
import { apiBaseUrl } from "../../auth/apiConfig";
import { mobileFetch } from "../../auth/mobileFetch";

export const assistantApi = new HealthApiClient(apiBaseUrl, mobileFetch);

export async function listActionProposals(
  state:
    | "pending"
    | "applied"
    | "rejected"
    | "expired"
    | "superseded" = "pending",
  cursor?: string,
) {
  return assistantApi.listActionProposals({ state, limit: 50, cursor });
}

export function editableProposalCommands(
  commands: components["schemas"]["ProposalState"]["commands"],
): string {
  return JSON.stringify(
    commands.map((command) => {
      if (command.action === "profile.create") {
        const { id: _id, ...draft } = command;
        return draft;
      }
      if (command.action === "event.create") {
        const {
          event_id: _eventId,
          observation_ids: _observationIds,
          ...draft
        } = command;
        return draft;
      }
      if (
        command.action === "goal.create" ||
        command.action === "plan.create" ||
        command.action === "tracker.create"
      ) {
        const { id: _id, ...draft } = command;
        return draft;
      }
      return command;
    }),
    null,
    2,
  );
}

export function mergeProposalSummaries(
  current: components["schemas"]["ProposalSummary"][],
  incoming: components["schemas"]["ProposalSummary"][],
): components["schemas"]["ProposalSummary"][] {
  const merged = new Map(current.map((item) => [item.id, item]));
  for (const item of incoming) {
    const existing = merged.get(item.id);
    if (
      !existing ||
      item.revision > existing.revision ||
      (item.revision === existing.revision &&
        Date.parse(item.updated_at) >= Date.parse(existing.updated_at))
    ) {
      merged.set(item.id, item);
    }
  }
  return [...merged.values()];
}
