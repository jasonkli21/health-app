import { ApiError, HealthApiClient } from "@personal-health/api-client";
import type { components } from "@personal-health/api-client";
import { mobileFetch } from "../../auth/mobileFetch";
import { apiBaseUrl } from "../../auth/apiConfig";
import { DailyCreateRecovery } from "../daily/api";

export const planningApi = new HealthApiClient(apiBaseUrl, mobileFetch);
export const activeTrackerCreateRecovery = new DailyCreateRecovery();
export type PlanningItem =
  | components["schemas"]["GoalResponse"]
  | components["schemas"]["RegimenResponse"]
  | components["schemas"]["PlanResponse"]
  | components["schemas"]["ContextResponse"]
  | components["schemas"]["TrackerResponse"];

export function planningErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 409) {
      return "This planning item changed. Reload it before trying again.";
    }
    if (error.status === 404) return "This planning item could not be found.";
    return (
      error.body?.message ?? "The planning request could not be completed."
    );
  }
  return "Could not reach your Health API. Check the connection and try again.";
}
