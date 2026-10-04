import { ApiError, ProfileApiClient } from "@personal-health/api-client";
import { mobileFetch } from "../../auth/mobileFetch";

const configuredApiUrl = process.env.EXPO_PUBLIC_API_URL?.trim();

export const profileApi = new ProfileApiClient(
  configuredApiUrl || "http://127.0.0.1:8000",
  mobileFetch,
);

export class ProfileUserError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ProfileUserError";
  }
}

export function profileErrorMessage(error: unknown): string {
  if (error instanceof ProfileUserError) return error.message;
  if (error instanceof ApiError) {
    if (error.status === 409) {
      return "This Profile item changed after you opened it. Reload the latest version before saving.";
    }
    if (error.status === 404) return "This Profile item could not be found.";
    return error.body?.message ?? "The Profile request could not be completed.";
  }
  return "Could not reach your Health API. Check the connection and try again.";
}
