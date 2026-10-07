import * as SecureStore from "expo-secure-store";

import { secureKeySegment } from "./secureKey";
import type { HealthKitResourceType } from "./types";

const DEFAULT_LOOKBACK_DAYS = 30;

function consentKey(
  ownerId: string,
  resourceType: HealthKitResourceType,
): string {
  return `hk.c.${secureKeySegment(ownerId)}.${resourceType}.healthkit-v1`;
}

function lookbackKey(ownerId: string): string {
  return `hk.l.${secureKeySegment(ownerId)}.healthkit-v1`;
}

export class HealthKitConsentStore {
  private static readonly versions = new Map<string, number>();

  version(ownerId: string, resourceType: HealthKitResourceType): number {
    return (
      HealthKitConsentStore.versions.get(
        `${secureKeySegment(ownerId)}.${resourceType}`,
      ) ?? 0
    );
  }

  async isEnabled(
    ownerId: string,
    resourceType: HealthKitResourceType,
  ): Promise<boolean> {
    return (
      (await SecureStore.getItemAsync(consentKey(ownerId, resourceType))) ===
      "enabled"
    );
  }

  async setEnabled(
    ownerId: string,
    resourceType: HealthKitResourceType,
    enabled: boolean,
  ): Promise<void> {
    const key = consentKey(ownerId, resourceType);
    const scope = `${secureKeySegment(ownerId)}.${resourceType}`;
    HealthKitConsentStore.versions.set(
      scope,
      (HealthKitConsentStore.versions.get(scope) ?? 0) + 1,
    );
    if (enabled) await SecureStore.setItemAsync(key, "enabled");
    else await SecureStore.deleteItemAsync(key);
  }

  async getLookbackDays(ownerId: string): Promise<number> {
    const stored = await SecureStore.getItemAsync(lookbackKey(ownerId));
    const value = stored ? Number(stored) : DEFAULT_LOOKBACK_DAYS;
    return Number.isInteger(value) && value >= 1 && value <= 90
      ? value
      : DEFAULT_LOOKBACK_DAYS;
  }

  async setLookbackDays(ownerId: string, value: number): Promise<void> {
    if (!Number.isInteger(value) || value < 1 || value > 90)
      throw new Error("Initial import lookback must be between 1 and 90 days.");
    await SecureStore.setItemAsync(lookbackKey(ownerId), String(value));
  }
}
