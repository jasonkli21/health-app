import type { HealthKitResourceType } from "./types";

export function checkpointKey(
  ownerId: string,
  deviceInstallationId: string,
  resourceType: HealthKitResourceType,
  policyVersion = "healthkit-v1",
): string {
  return [
    "healthkit",
    ownerId,
    deviceInstallationId,
    resourceType,
    policyVersion,
  ].join(":");
}
