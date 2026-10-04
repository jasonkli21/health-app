import { ApiError } from "@personal-health/api-client";

import { ProfileUserError } from "./api";
import type { BuiltProfileFields } from "./model";

export type ProfileCreateAttempt = {
  id: string;
  fields: BuiltProfileFields;
};

function stableJson(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(stableJson).join(",")}]`;
  }
  if (typeof value === "object" && value !== null) {
    const object = value as Record<string, unknown>;
    return `{${Object.keys(object)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableJson(object[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value) ?? "undefined";
}

export function isDefinitiveCreateFailure(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    [400, 401, 403, 404, 413, 415, 422].includes(error.status)
  );
}

export class ProfileCreateRecovery {
  private uncertainAttempt: ProfileCreateAttempt | null = null;

  get isUncertain(): boolean {
    return this.uncertainAttempt !== null;
  }

  prepare(id: string, fields: BuiltProfileFields): ProfileCreateAttempt {
    if (!this.uncertainAttempt) return { id, fields };
    if (stableJson(fields) !== stableJson(this.uncertainAttempt.fields)) {
      throw new ProfileUserError(
        "A previous save may have completed. Retry the original save to recover its result before submitting these edits.",
      );
    }
    return this.uncertainAttempt;
  }

  retryOriginal(): ProfileCreateAttempt | null {
    return this.uncertainAttempt;
  }

  markFailure(attempt: ProfileCreateAttempt, error: unknown): boolean {
    if (isDefinitiveCreateFailure(error)) {
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

// An in-memory app-level recovery record survives route unmounts and refocuses.
export const activeProfileCreateRecovery = new ProfileCreateRecovery();
