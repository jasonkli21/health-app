import { describe, expect, it } from "vitest";

import type { SessionSnapshot } from "../src/auth/sessionStore";
import {
  HealthKitCheckpointConflictError,
  HealthKitSyncAuthorizationError,
  HealthKitSyncCoordinator,
} from "../src/integrations/healthkit/coordinator";
import type { CheckpointStore } from "../src/integrations/healthkit/checkpoint";
import type { HealthKitConsentStore } from "../src/integrations/healthkit/consent";
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

class MemoryCheckpointStore implements CheckpointStore {
  values = new Map<string, HealthKitCheckpoint>();
  saves: string[] = [];
  fail = false;

  async load(key: string): Promise<HealthKitCheckpoint | null> {
    return this.values.get(key) ?? null;
  }

  async save(key: string, checkpoint: HealthKitCheckpoint): Promise<void> {
    this.saves.push(key);
    if (this.fail) throw new Error("secure storage unavailable");
    this.values.set(key, checkpoint);
  }
}

class MemoryConsentStore {
  enabled = true;
  private currentVersion = 0;

  version(): number {
    return this.currentVersion;
  }

  async isEnabled(): Promise<boolean> {
    return this.enabled;
  }

  disable(): void {
    this.enabled = false;
    this.currentVersion += 1;
  }
}

class MemorySessionStore {
  snapshot: SessionSnapshot = {
    mode: "firebase",
    status: "signed_in",
    epoch: 1,
    userId: "owner-1",
    email: null,
    message: null,
  };

  getSnapshot(): SessionSnapshot {
    return this.snapshot;
  }
}

function harness() {
  const checkpoints = new MemoryCheckpointStore();
  const consents = new MemoryConsentStore();
  const sessions = new MemorySessionStore();
  let uploads = 0;
  const coordinator = new HealthKitSyncCoordinator(
    (guard) => ({
      async importHealthKitBatch() {
        uploads += 1;
        await guard();
        return receipt;
      },
    }),
    checkpoints,
    sessions,
    consents as unknown as HealthKitConsentStore,
  );
  return {
    coordinator,
    checkpoints,
    consents,
    sessions,
    uploadCount: () => uploads,
  };
}

async function authorization(
  coordinator: HealthKitSyncCoordinator,
  ownerId = "owner-1",
  resourceType: HealthKitBatchBody["resource_type"] = "workouts",
) {
  return coordinator.captureAuthorization({
    ownerId,
    deviceInstallationId: request.device_installation_id,
    resourceType,
  });
}

describe("HealthKit sync coordinator", () => {
  it("captures account and consent before reads, then saves only after ACK", async () => {
    const h = harness();
    const auth = await authorization(h.coordinator);
    const result = await h.coordinator.commitBatch({
      authorization: auth,
      request,
      nextAnchor: "opaque-anchor",
      now: () => new Date("2026-10-07T20:00:00Z"),
    });
    const key = checkpointKey(
      auth.ownerId,
      auth.deviceInstallationId,
      auth.resourceType,
      auth.policyVersion,
    );
    expect(result.status).toBe("saved");
    expect(h.uploadCount()).toBe(1);
    expect(h.checkpoints.values.get(key)?.anchor).toBe("opaque-anchor");
    expect(h.checkpoints.values.get(key)?.ownerId).toBe("owner-1");
  });

  it("rejects unconsented or account-mismatched preparation", async () => {
    const h = harness();
    h.consents.disable();
    await expect(authorization(h.coordinator)).rejects.toBeInstanceOf(
      HealthKitSyncAuthorizationError,
    );
    expect(h.uploadCount()).toBe(0);

    h.consents.enabled = true;
    h.sessions.snapshot = {
      ...h.sessions.snapshot,
      userId: "owner-2",
      epoch: 2,
    };
    await expect(authorization(h.coordinator)).rejects.toBeInstanceOf(
      HealthKitSyncAuthorizationError,
    );
  });

  it("does not upload after the account or type consent changes during token acquisition", async () => {
    for (const changed of ["account", "consent"] as const) {
      const h = harness();
      const auth = await authorization(h.coordinator);
      let resume!: () => void;
      const waiting = new Promise<void>((resolve) => {
        resume = resolve;
      });
      const guarded = new HealthKitSyncCoordinator(
        (guard) => ({
          async importHealthKitBatch() {
            await waiting;
            await guard();
            return receipt;
          },
        }),
        h.checkpoints,
        h.sessions,
        h.consents as unknown as HealthKitConsentStore,
      );
      const commit = guarded.commitBatch({
        authorization: auth,
        request,
        nextAnchor: "next",
      });
      await Promise.resolve();
      if (changed === "account") {
        h.sessions.snapshot = {
          ...h.sessions.snapshot,
          userId: "owner-2",
          epoch: 2,
        };
      } else {
        h.consents.disable();
      }
      resume();
      await expect(commit).rejects.toBeInstanceOf(
        HealthKitSyncAuthorizationError,
      );
      expect(h.checkpoints.values.size).toBe(0);
    }
  });

  it("prevents an older prepared sync from replacing a newer anchor", async () => {
    const h = harness();
    const older = await authorization(h.coordinator);
    const newer = { ...older };
    await h.coordinator.commitBatch({
      authorization: newer,
      request,
      nextAnchor: "new-anchor",
    });
    await expect(
      h.coordinator.commitBatch({
        authorization: older,
        request,
        nextAnchor: "old-anchor",
      }),
    ).rejects.toBeInstanceOf(HealthKitCheckpointConflictError);
    const key = checkpointKey(
      older.ownerId,
      older.deviceInstallationId,
      older.resourceType,
      older.policyVersion,
    );
    expect(h.checkpoints.values.get(key)?.anchor).toBe("new-anchor");
    expect(h.uploadCount()).toBe(1);
  });

  it("rechecks checkpoint scope immediately before upload", async () => {
    const h = harness();
    const auth = await authorization(h.coordinator);
    const key = checkpointKey(
      auth.ownerId,
      auth.deviceInstallationId,
      auth.resourceType,
      auth.policyVersion,
    );
    h.checkpoints.values.set(key, {
      ownerId: "owner-2",
      deviceInstallationId: auth.deviceInstallationId,
      resourceType: auth.resourceType,
      policyVersion: auth.policyVersion,
      anchor: null,
      savedAt: "2026-10-07T20:00:00Z",
    });
    await expect(
      h.coordinator.commitBatch({
        authorization: auth,
        request,
        nextAnchor: "next",
      }),
    ).rejects.toBeInstanceOf(HealthKitSyncAuthorizationError);
    expect(h.uploadCount()).toBe(0);
  });

  it("durably recovers an acknowledged checkpoint before accepting more work", async () => {
    const h = harness();
    const auth = await authorization(h.coordinator);
    h.checkpoints.fail = true;
    const result = await h.coordinator.commitBatch({
      authorization: auth,
      request,
      nextAnchor: "acknowledged-anchor",
    });
    expect(result.status).toBe("acknowledged_checkpoint_pending");

    h.checkpoints.fail = false;
    await expect(
      h.coordinator.commitBatch({
        authorization: auth,
        request,
        nextAnchor: "later-anchor",
      }),
    ).rejects.toBeInstanceOf(HealthKitCheckpointConflictError);
    const key = checkpointKey(
      auth.ownerId,
      auth.deviceInstallationId,
      auth.resourceType,
      auth.policyVersion,
    );
    expect(h.checkpoints.values.get(key)?.anchor).toBe("acknowledged-anchor");
    expect(h.uploadCount()).toBe(1);
  });

  it("serializes only the same authorization scope", async () => {
    const h = harness();
    const authA = await authorization(h.coordinator);
    let resume!: () => void;
    const waiting = new Promise<void>((resolve) => {
      resume = resolve;
    });
    let first = true;
    const coordinator = new HealthKitSyncCoordinator(
      (guard) => ({
        async importHealthKitBatch() {
          if (first) {
            first = false;
            await waiting;
          }
          await guard();
          return receipt;
        },
      }),
      h.checkpoints,
      h.sessions,
      h.consents as unknown as HealthKitConsentStore,
    );
    const firstCommit = coordinator.commitBatch({
      authorization: authA,
      request,
      nextAnchor: "first-anchor",
    });
    const independentAuth = await coordinator.captureAuthorization({
      ownerId: "owner-1",
      deviceInstallationId: "another-installation",
      resourceType: "workouts",
    });
    const independentRequest = {
      ...request,
      device_installation_id: independentAuth.deviceInstallationId,
      batch_id: "20a899f7-1f16-44e9-88c8-5c31b3f6cdd7",
    };
    const independent = coordinator.commitBatch({
      authorization: independentAuth,
      request: independentRequest,
      nextAnchor: "independent-anchor",
    });
    await expect(independent).resolves.toMatchObject({ status: "saved" });
    resume();
    await expect(firstCommit).resolves.toMatchObject({ status: "saved" });
  });
});
