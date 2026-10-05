import { ApiError, HealthApiClient } from "@personal-health/api-client";
import { mobileFetch } from "../../auth/mobileFetch";
import { apiBaseUrl } from "../../auth/apiConfig";

import type { DailyCreateRequest, DailyDomain, DailyDraft } from "./model";

export const dailyApi = new HealthApiClient(apiBaseUrl, mobileFetch);

export class DailyUserError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "DailyUserError";
  }
}

export function dailyErrorMessage(error: unknown): string {
  if (error instanceof DailyUserError) return error.message;
  if (error instanceof ApiError) {
    if (error.status === 409) {
      return "This entry changed or its save result needs recovery. Reload the latest entry before saving.";
    }
    if (error.status === 404) return "This entry could not be found.";
    return error.body?.message ?? "The daily request could not be completed.";
  }
  return "Could not reach your Health API. Check the connection and try again.";
}

export function isDefinitiveDailyCreateFailure(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    [400, 401, 403, 404, 409, 413, 415, 422].includes(error.status)
  );
}

export type DailyCreateAttempt = {
  request: DailyCreateRequest;
  primaryId: string;
  domain: DailyDomain;
  draft: DailyDraft;
  sessionEpoch?: number;
  sessionUserId?: string | null;
};

export function isDailyCreateAttemptCurrent(
  attempt: DailyCreateAttempt,
  session: { epoch: number; userId: string | null },
): boolean {
  return (
    attempt.sessionEpoch === undefined ||
    (attempt.sessionEpoch === session.epoch &&
      attempt.sessionUserId === session.userId)
  );
}

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

export class DailyCreateRecovery {
  private uncertainAttempt: DailyCreateAttempt | null = null;

  get isUncertain(): boolean {
    return this.uncertainAttempt !== null;
  }

  prepare(attempt: DailyCreateAttempt): DailyCreateAttempt {
    if (!this.uncertainAttempt) return attempt;
    if (
      stableJson(attempt.request) !== stableJson(this.uncertainAttempt.request)
    ) {
      throw new DailyUserError(
        "A previous save may have completed. Retry the original save to recover it before changing these details.",
      );
    }
    return this.uncertainAttempt;
  }

  retryOriginal(): DailyCreateAttempt | null {
    return this.uncertainAttempt;
  }

  markFailure(attempt: DailyCreateAttempt, error: unknown): boolean {
    if (isDefinitiveDailyCreateFailure(error)) {
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

export const activeDailyCreateRecovery = new DailyCreateRecovery();
