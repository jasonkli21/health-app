import { ApiError, HealthApiClient } from "@personal-health/api-client";
import type { components } from "@personal-health/api-client";
import { mobileFetch } from "../../auth/mobileFetch";
import { apiBaseUrl } from "../../auth/apiConfig";
import { DailyCreateRecovery } from "../daily/api";

export const planningApi = new HealthApiClient(apiBaseUrl, mobileFetch);
export const activeTrackerCreateRecovery = new DailyCreateRecovery();

export type PlanningCreateAttempt =
  | {
      kind: "goal";
      body: components["schemas"]["GoalCreateRequest"];
      sessionEpoch: number;
      sessionUserId: string | null;
    }
  | {
      kind: "regimen";
      body: components["schemas"]["RegimenCreateRequest"];
      sessionEpoch: number;
      sessionUserId: string | null;
    }
  | {
      kind: "plan";
      body: components["schemas"]["PlanCreateRequest"];
      sessionEpoch: number;
      sessionUserId: string | null;
    }
  | {
      kind: "context";
      body: components["schemas"]["ContextCreateRequest"];
      sessionEpoch: number;
      sessionUserId: string | null;
    }
  | {
      kind: "tracker_definition";
      body: components["schemas"]["TrackerCreateRequest"];
      sessionEpoch: number;
      sessionUserId: string | null;
    };

function stableJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (typeof value === "object" && value !== null) {
    const object = value as Record<string, unknown>;
    return `{${Object.keys(object)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableJson(object[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value) ?? "undefined";
}

export class PlanningCreateRecovery {
  private uncertainAttempt: PlanningCreateAttempt | null = null;

  retryOriginal(): PlanningCreateAttempt | null {
    return this.uncertainAttempt;
  }

  prepare(attempt: PlanningCreateAttempt): PlanningCreateAttempt {
    if (!this.uncertainAttempt) return attempt;
    if (
      this.uncertainAttempt.sessionEpoch !== attempt.sessionEpoch ||
      this.uncertainAttempt.sessionUserId !== attempt.sessionUserId
    ) {
      throw new Error(
        "A previous account's save must be cleared before creating another item.",
      );
    }
    if (
      stableJson({ kind: attempt.kind, body: attempt.body }) !==
      stableJson({
        kind: this.uncertainAttempt.kind,
        body: this.uncertainAttempt.body,
      })
    ) {
      throw new Error(
        "Retry the original planning save before changing its details.",
      );
    }
    return this.uncertainAttempt;
  }

  markFailure(attempt: PlanningCreateAttempt, error: unknown): boolean {
    if (
      error instanceof ApiError &&
      [400, 401, 403, 404, 409, 413, 415, 422].includes(error.status)
    ) {
      this.uncertainAttempt = null;
      return false;
    }
    this.uncertainAttempt = attempt;
    return true;
  }

  resolve(): void {
    this.uncertainAttempt = null;
  }
}

export const activePlanningCreateRecovery = new PlanningCreateRecovery();

export async function sendPlanningCreate(
  attempt: PlanningCreateAttempt,
): Promise<void> {
  if (attempt.kind === "goal") await planningApi.createGoal(attempt.body);
  else if (attempt.kind === "regimen")
    await planningApi.createRegimen(attempt.body);
  else if (attempt.kind === "plan") await planningApi.createPlan(attempt.body);
  else if (attempt.kind === "context")
    await planningApi.createContext(attempt.body);
  else await planningApi.createTracker(attempt.body);
}

export function isPlanningCreateAttemptCurrent(
  attempt: PlanningCreateAttempt,
  session: { epoch: number; userId: string | null },
): boolean {
  return (
    attempt.sessionEpoch === session.epoch &&
    attempt.sessionUserId === session.userId
  );
}

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
