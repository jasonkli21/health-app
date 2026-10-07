import * as SecureStore from "expo-secure-store";

import type { HealthKitCheckpoint } from "./types";

export interface CheckpointStore {
  load(key: string): Promise<HealthKitCheckpoint | null>;
  save(key: string, checkpoint: HealthKitCheckpoint): Promise<void>;
}

export class SecureCheckpointStore implements CheckpointStore {
  async load(key: string): Promise<HealthKitCheckpoint | null> {
    const saved = await SecureStore.getItemAsync(key);
    if (!saved) return null;
    try {
      const parsed = JSON.parse(saved) as HealthKitCheckpoint;
      if (
        parsed.ownerId === undefined ||
        parsed.deviceInstallationId === undefined ||
        parsed.policyVersion !== "healthkit-v1"
      )
        return null;
      return parsed;
    } catch {
      return null;
    }
  }

  async save(key: string, checkpoint: HealthKitCheckpoint): Promise<void> {
    await SecureStore.setItemAsync(key, JSON.stringify(checkpoint));
  }
}
