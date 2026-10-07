import { describe, expect, it } from "vitest";

import { HealthKitSyncCoordinator } from "../src/integrations/healthkit/coordinator";
import { checkpointKey } from "../src/integrations/healthkit/checkpointKey";
import type {
  HealthKitBatchBody,
  HealthKitBatchResult,
  HealthKitCheckpoint,
} from "../src/integrations/healthkit/types";

const request: HealthKitBatchBody = {
  batch_id: "20a899f7-1f16-44e9-88c8-5c31b3f6cdd6",
  device_installation_id: "4bcf0eac-f815-4a88-bb6d-d10c477b8eab",
  resource_type: "workouts",
  policy_version: "healthkit-v1",
  entries: [],
  tombstones: [],
};

const receipt: HealthKitBatchResult = {
  batch_id: request.batch_id,
  replayed: false,
  created_count: 1,
  updated_count: 0,
  unchanged_count: 0,
  tombstoned_count: 0,
  correction_count: 0,
  conflict_count: 0,
};

class MemoryCheckpointStore {
  calls: string[] = [];
  saved: HealthKitCheckpoint | null = null;
  fail = false;

  async load(): Promise<HealthKitCheckpoint | null> {
    return this.saved;
  }

  async save(key: string, checkpoint: HealthKitCheckpoint): Promise<void> {
    this.calls.push(`checkpoint:${key}`);
    if (this.fail) throw new Error("secure storage unavailable");
    this.saved = checkpoint;
  }
}

describe("HealthKit checkpoint coordinator", () => {
  it("saves an opaque anchor only after the server acknowledges the batch", async () => {
    const order: string[] = [];
    const store = new MemoryCheckpointStore();
    const api = {
      async importHealthKitBatch(): Promise<HealthKitBatchResult> {
        order.push("ack");
        return receipt;
      },
    };
    const coordinator = new HealthKitSyncCoordinator(api, store);
    const result = await coordinator.commitBatch({
      ownerId: "owner-1",
      deviceInstallationId: request.device_installation_id,
      resourceType: "workouts",
      consented: true,
      request,
      nextAnchor: "opaque-anchor",
      now: () => new Date("2026-10-07T20:00:00Z"),
    });
    order.push(...store.calls);
    expect(result.status).toBe("saved");
    expect(order[0]).toBe("ack");
    expect(store.saved?.anchor).toBe("opaque-anchor");
    expect(store.saved?.ownerId).toBe("owner-1");
  });

  it("does not advance the checkpoint without explicit type consent", async () => {
    let uploads = 0;
    const store = new MemoryCheckpointStore();
    const api = {
      async importHealthKitBatch(): Promise<HealthKitBatchResult> {
        uploads += 1;
        return receipt;
      },
    };
    const coordinator = new HealthKitSyncCoordinator(api, store);
    await expect(
      coordinator.commitBatch({
        ownerId: "owner-1",
        deviceInstallationId: request.device_installation_id,
        resourceType: "workouts",
        consented: false,
        request,
        nextAnchor: "opaque-anchor",
      }),
    ).rejects.toThrow("consent is required");
    expect(uploads).toBe(0);
    expect(store.saved).toBeNull();
  });

  it("surfaces acknowledged uploads when secure checkpoint storage fails", async () => {
    const store = new MemoryCheckpointStore();
    store.fail = true;
    const api = { importHealthKitBatch: async () => receipt };
    const coordinator = new HealthKitSyncCoordinator(api, store);
    const result = await coordinator.commitBatch({
      ownerId: "owner-1",
      deviceInstallationId: request.device_installation_id,
      resourceType: "workouts",
      consented: true,
      request,
      nextAnchor: "opaque-anchor",
    });
    expect(result.status).toBe("acknowledged_checkpoint_pending");
  });

  it("isolates checkpoints by account, installation, type, and policy", () => {
    expect(
      checkpointKey("owner-a", "installation-a", "steps", "healthkit-v1"),
    ).not.toBe(
      checkpointKey("owner-b", "installation-a", "steps", "healthkit-v1"),
    );
  });
});
