import * as SecureStore from "expo-secure-store";

import { secureKeySegment } from "./secureKey";
import type { HealthKitCheckpoint } from "./types";

const CHECKPOINT_INDEX_KEY = "healthkit.checkpoint.index.v1";

export interface CheckpointStore {
  load(key: string): Promise<HealthKitCheckpoint | null>;
  save(key: string, checkpoint: HealthKitCheckpoint): Promise<void>;
}

export class SecureCheckpointStore implements CheckpointStore {
  private static mutationQueue: Promise<void> = Promise.resolve();

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
    await this.withMutation(async () => {
      const keys = await this.loadKeys();
      if (!keys.includes(key)) {
        await SecureStore.setItemAsync(
          CHECKPOINT_INDEX_KEY,
          JSON.stringify([...keys, key]),
        );
      }
      await SecureStore.setItemAsync(key, JSON.stringify(checkpoint));
    });
  }

  async clearOwner(ownerId: string): Promise<void> {
    await this.withMutation(async () => {
      const keys = await this.loadKeys();
      const retained: string[] = [];
      for (const key of keys) {
        const checkpoint = await this.load(key);
        if (
          key.startsWith(`healthkit.${secureKeySegment(ownerId)}.`) ||
          checkpoint?.ownerId === ownerId
        ) {
          await SecureStore.deleteItemAsync(key);
        } else {
          retained.push(key);
        }
      }
      await SecureStore.setItemAsync(
        CHECKPOINT_INDEX_KEY,
        JSON.stringify(retained),
      );
    });
  }

  private async loadKeys(): Promise<string[]> {
    const stored = await SecureStore.getItemAsync(CHECKPOINT_INDEX_KEY);
    if (!stored) return [];
    try {
      const parsed: unknown = JSON.parse(stored);
      if (
        !Array.isArray(parsed) ||
        parsed.some((key) => typeof key !== "string" || key.length > 256)
      )
        return [];
      return [...new Set(parsed)];
    } catch {
      return [];
    }
  }

  private async withMutation(action: () => Promise<void>): Promise<void> {
    const next = SecureCheckpointStore.mutationQueue.then(action);
    SecureCheckpointStore.mutationQueue = next.catch(() => undefined);
    await next;
  }
}
