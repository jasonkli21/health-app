import { HealthApiClient } from "@personal-health/api-client";
import { apiBaseUrl } from "../../auth/apiConfig";
import { mobileFetch } from "../../auth/mobileFetch";

export const assistantApi = new HealthApiClient(apiBaseUrl, mobileFetch);

export async function listActionProposals() {
  return assistantApi.listActionProposals({ limit: 50 });
}
