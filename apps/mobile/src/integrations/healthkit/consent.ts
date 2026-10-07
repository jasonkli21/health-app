import * as SecureStore from "expo-secure-store";

import type { HealthKitResourceType } from "./types";

const DEFAULT_LOOKBACK_DAYS = 30;

function consentKey(
  ownerId: string,
  resourceType: HealthKitResourceType,
): string {
  return `healthkit:consent:${ownerId}:${resourceType}:healthkit-v1`;
}

function lookbackKey(ownerId: string): string {
  return `healthkit:lookback:${ownerId}:healthkit-v1`;
}

export class HealthKitConsentStore {
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
