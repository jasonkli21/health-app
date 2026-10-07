import { ApiError, HealthApiClient } from "@personal-health/api-client";
import { apiBaseUrl } from "../../auth/apiConfig";
import { mobileFetch } from "../../auth/mobileFetch";

export const insightsApi = new HealthApiClient(apiBaseUrl, mobileFetch);

export function insightsErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 409)
      return "This item changed. Reload the latest version before trying again.";
    if (error.status === 404) return "This analytics item could not be found.";
    return (
      error.body?.message ?? "The analytics request could not be completed."
    );
  }
  return "Could not reach your Health API. Check the connection and try again.";
}
