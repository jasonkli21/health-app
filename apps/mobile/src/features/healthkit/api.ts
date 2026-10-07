import { HealthApiClient } from "@personal-health/api-client";

import { apiBaseUrl } from "../../auth/apiConfig";
import { mobileFetch } from "../../auth/mobileFetch";

export const healthkitApi = new HealthApiClient(apiBaseUrl, mobileFetch);

export function healthkitErrorMessage(): string {
  return "HealthKit settings could not be loaded. Check the connection and try again.";
}
