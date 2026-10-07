import { HealthApiClient } from "@personal-health/api-client";

import { apiBaseUrl } from "../../auth/apiConfig";
import { mobileFetch } from "../../auth/mobileFetch";

export const accountDataApi = new HealthApiClient(apiBaseUrl, mobileFetch);

export function createDeletionRequestId(): string {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (part) => {
    const random = Math.floor(Math.random() * 16);
    const value = part === "x" ? random : (random & 0x3) | 0x8;
    return value.toString(16);
  });
}
