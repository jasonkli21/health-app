import type { operations } from "@personal-health/api-client";

export type HealthKitBatchBody =
  operations["importHealthKitBatch"]["requestBody"];
export type HealthKitResourceType = HealthKitBatchBody["resource_type"];
export type HealthKitImportEntry = NonNullable<
  HealthKitBatchBody["entries"]
>[number];
export type HealthKitImportMetadata = NonNullable<
  HealthKitImportEntry["metadata"]
>;
export type HealthKitBatchResult =
  operations["importHealthKitBatch"]["responses"]["201"];

export type NormalizedHealthSample = {
  sourceSampleId: string;
  record: HealthKitImportEntry["record"];
  metadata: HealthKitImportMetadata;
};

export type HealthKitCheckpoint = {
  ownerId: string;
  deviceInstallationId: string;
  resourceType: HealthKitResourceType;
  policyVersion: "healthkit-v1";
  anchor: string | null;
  savedAt: string;
};
