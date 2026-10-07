import * as SecureStore from "expo-secure-store";

import { checkpointKey } from "./checkpointKey";
import { secureKeySegment } from "./secureKey";
import type { HealthKitCheckpoint } from "./types";

const CHECKPOINT_INDEX_KEY = "healthkit.checkpoint.index.v1";
const MAX_IDENTITY_LENGTH = 256;
const MAX_CHECKPOINT_KEY_LENGTH = 4096;
const MAX_INDEX_BYTES = 1024 * 1024;
const MAX_INDEX_KEYS = 4096;

export interface CheckpointStore {
  load(key: string): Promise<HealthKitCheckpoint | null>;
  save(key: string, checkpoint: HealthKitCheckpoint): Promise<void>;
}

export class SecureCheckpointStore implements CheckpointStore {
  private static mutationQueue: Promise<void> = Promise.resolve();

  async load(key: string): Promise<HealthKitCheckpoint | null> {
    validateCheckpointKey(key);
    const saved = await SecureStore.getItemAsync(key);
    if (!saved) return null;
    try {
      const parsed: unknown = JSON.parse(saved);
      if (
        typeof parsed !== "object" ||
        parsed === null ||
        !("ownerId" in parsed) ||
        !validIdentity(parsed.ownerId) ||
        !("deviceInstallationId" in parsed) ||
        !validIdentity(parsed.deviceInstallationId) ||
        !("resourceType" in parsed) ||
        !isResourceType(parsed.resourceType) ||
        !("policyVersion" in parsed) ||
        parsed.policyVersion !== "healthkit-v1" ||
        key !==
          checkpointKey(
            parsed.ownerId,
            parsed.deviceInstallationId,
            parsed.resourceType,
            parsed.policyVersion,
          )
      )
        return null;
      return parsed as HealthKitCheckpoint;
    } catch {
      return null;
    }
  }

  async save(key: string, checkpoint: HealthKitCheckpoint): Promise<void> {
    validateCheckpointKey(key);
    validateCheckpoint(checkpoint);
    if (
      key !==
      checkpointKey(
        checkpoint.ownerId,
        checkpoint.deviceInstallationId,
        checkpoint.resourceType,
        checkpoint.policyVersion,
      )
    )
      throw new Error(
        "Checkpoint key does not match its owner and installation.",
      );
    await this.withMutation(async () => {
      const keys = await this.loadKeys();
      if (!keys.includes(key)) {
        const nextKeys = [...keys, key];
        const indexValue = JSON.stringify(nextKeys);
        if (
          nextKeys.length > MAX_INDEX_KEYS ||
          indexValue.length > MAX_INDEX_BYTES
        )
          throw new Error("Checkpoint index exceeds its supported size.");
        await SecureStore.setItemAsync(CHECKPOINT_INDEX_KEY, indexValue);
      }
      await SecureStore.setItemAsync(key, JSON.stringify(checkpoint));
    });
  }

  async clearOwner(ownerId: string): Promise<void> {
    if (!validIdentity(ownerId))
      throw new Error("Checkpoint owner identity is invalid.");
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
    if (stored.length > MAX_INDEX_BYTES)
      throw new Error("Checkpoint index exceeds its supported size.");
    try {
      const parsed: unknown = JSON.parse(stored);
      if (
        !Array.isArray(parsed) ||
        parsed.length > MAX_INDEX_KEYS ||
        parsed.some((key) => {
          try {
            validateCheckpointKey(key);
            return false;
          } catch {
            return true;
          }
        })
      )
        throw new Error("Checkpoint index is invalid.");
      return [...new Set(parsed as string[])];
    } catch {
      throw new Error("Checkpoint index is invalid.");
    }
  }

  private async withMutation(action: () => Promise<void>): Promise<void> {
    const next = SecureCheckpointStore.mutationQueue.then(action);
    SecureCheckpointStore.mutationQueue = next.catch(() => undefined);
    await next;
  }
}

function validIdentity(value: unknown): value is string {
  return (
    typeof value === "string" &&
    value.length > 0 &&
    value.length <= MAX_IDENTITY_LENGTH
  );
}

function validateCheckpointKey(key: unknown): asserts key is string {
  if (
    typeof key !== "string" ||
    key.length > MAX_CHECKPOINT_KEY_LENGTH ||
    !/^healthkit\.[\w.-]+\.[\w.-]+\.[a-z_]+\.[\w.-]+$/.test(key)
  )
    throw new Error("Checkpoint key is invalid.");
}

function validateCheckpoint(checkpoint: HealthKitCheckpoint): void {
  if (
    !validIdentity(checkpoint.ownerId) ||
    !validIdentity(checkpoint.deviceInstallationId) ||
    !isResourceType(checkpoint.resourceType) ||
    checkpoint.policyVersion !== "healthkit-v1"
  )
    throw new Error("Checkpoint identity is invalid.");
}

function isResourceType(
  value: unknown,
): value is HealthKitCheckpoint["resourceType"] {
  return (
    value === "steps" ||
    value === "sleep" ||
    value === "workouts" ||
    value === "weight" ||
    value === "resting_heart_rate" ||
    value === "heart_rate_summary"
  );
}
