import { HealthApiClient, type FetchLike } from "@personal-health/api-client";

import { apiBaseUrl } from "../../auth/apiConfig";
import type { HealthKitGuardedRequestInit } from "../../auth/authenticatedFetch";
import { mobileFetch } from "../../auth/mobileFetch";

export const healthkitApi = new HealthApiClient(apiBaseUrl, mobileFetch);

export function healthkitSyncApiForGuard(
  guard: () => Promise<void>,
): HealthApiClient {
  const guardedFetch: FetchLike = (input, init) =>
    mobileFetch(input, {
      ...(init ?? { method: "GET" }),
      healthkitGuard: guard,
    } as HealthKitGuardedRequestInit);
  return new HealthApiClient(apiBaseUrl, guardedFetch);
}

export function healthkitErrorMessage(): string {
  return "HealthKit settings could not be loaded. Check the connection and try again.";
}
