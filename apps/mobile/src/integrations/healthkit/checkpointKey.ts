import type { HealthKitResourceType } from "./types";
import { secureKeySegment } from "./secureKey";

export function checkpointKey(
  ownerId: string,
  deviceInstallationId: string,
  resourceType: HealthKitResourceType,
  policyVersion = "healthkit-v1",
): string {
  return [
    "healthkit",
    secureKeySegment(ownerId),
    secureKeySegment(deviceInstallationId),
    resourceType,
    secureKeySegment(policyVersion),
  ].join(".");
}
