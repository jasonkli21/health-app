import type { HealthApiClient } from "@personal-health/api-client";

import type { CheckpointStore } from "./checkpoint";
import { checkpointKey } from "./checkpointKey";
import type {
  HealthKitBatchBody,
  HealthKitBatchResult,
  HealthKitCheckpoint,
  HealthKitResourceType,
} from "./types";

export type SyncBatchInput = {
  ownerId: string;
  deviceInstallationId: string;
  resourceType: HealthKitResourceType;
  consented: boolean;
  request: HealthKitBatchBody;
  nextAnchor: string | null;
  now?: () => Date;
};

export type SyncBatchResult =
  | { status: "saved"; receipt: HealthKitBatchResult }
  | {
      status: "acknowledged_checkpoint_pending";
      receipt: HealthKitBatchResult;
    };

export class HealthKitSyncCoordinator {
  constructor(
    private readonly api: Pick<HealthApiClient, "importHealthKitBatch">,
    private readonly checkpoints: CheckpointStore,
  ) {}

  async commitBatch(input: SyncBatchInput): Promise<SyncBatchResult> {
    if (!input.consented)
      throw new Error("HealthKit sync consent is required.");
    if (
      input.request.device_installation_id !== input.deviceInstallationId ||
      input.request.resource_type !== input.resourceType
    )
      throw new Error("HealthKit batch does not match its checkpoint scope.");

    const receipt = await this.api.importHealthKitBatch(input.request);
    const checkpoint: HealthKitCheckpoint = {
      ownerId: input.ownerId,
      deviceInstallationId: input.deviceInstallationId,
      resourceType: input.resourceType,
      policyVersion: input.request.policy_version,
      anchor: input.nextAnchor,
      savedAt: (input.now ?? (() => new Date()))().toISOString(),
    };
    try {
      await this.checkpoints.save(
        checkpointKey(
          input.ownerId,
          input.deviceInstallationId,
          input.resourceType,
          input.request.policy_version,
        ),
        checkpoint,
      );
      return { status: "saved", receipt };
    } catch {
      return { status: "acknowledged_checkpoint_pending", receipt };
    }
  }
}
