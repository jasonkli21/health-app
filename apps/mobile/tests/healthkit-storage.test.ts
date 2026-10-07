import { beforeEach, describe, expect, it, vi } from "vitest";
import * as SecureStore from "expo-secure-store";

import { SecureCheckpointStore } from "../src/integrations/healthkit/checkpoint";
import { HealthKitConsentStore } from "../src/integrations/healthkit/consent";
import { checkpointKey } from "../src/integrations/healthkit/checkpointKey";
import { secureKeySegment } from "../src/integrations/healthkit/secureKey";

const secureStoreMock = vi.hoisted(() => ({
  values: new Map<string, string>(),
  keys: new Set<string>(),
  fail: false,
}));

vi.mock("expo-secure-store", () => {
  const validateKey = (key: string) => {
    if (!/^[\w.-]+$/.test(key)) throw new Error("Invalid SecureStore key");
    secureStoreMock.keys.add(key);
  };
  return {
    getItemAsync: async (key: string) => {
      validateKey(key);
      if (secureStoreMock.fail) throw new Error("SecureStore unavailable");
      return secureStoreMock.values.get(key) ?? null;
    },
    setItemAsync: async (key: string, value: string) => {
      validateKey(key);
      if (secureStoreMock.fail) throw new Error("SecureStore unavailable");
      secureStoreMock.values.set(key, value);
    },
    deleteItemAsync: async (key: string) => {
      validateKey(key);
      if (secureStoreMock.fail) throw new Error("SecureStore unavailable");
      secureStoreMock.values.delete(key);
    },
  };
});

beforeEach(() => {
  secureStoreMock.values.clear();
  secureStoreMock.keys.clear();
  secureStoreMock.fail = false;
});

describe("HealthKit secure storage", () => {
  it("encodes arbitrary accounts into SecureStore's supported key alphabet", async () => {
    const ownerId = "owner:α/💓.with_odd-chars";
    const consent = new HealthKitConsentStore();
    await consent.setEnabled(ownerId, "sleep", true);
    await consent.setLookbackDays(ownerId, 90);
    expect(await consent.isEnabled(ownerId, "sleep")).toBe(true);
    expect(await consent.getLookbackDays(ownerId)).toBe(90);

    const key = checkpointKey(ownerId, "install:one/💓", "sleep");
    expect(key).toMatch(/^[\w.-]+$/);
    await SecureStore.setItemAsync(key, "opaque-anchor");
    expect(await SecureStore.getItemAsync(key)).toBe("opaque-anchor");
    expect(secureStoreMock.keys).toContain(key);
    expect(secureKeySegment("a:b")).not.toBe(secureKeySegment("a.b"));
    expect(secureKeySegment("💓")).toMatch(/^[\da-f]+$/);
    await expect(
      SecureStore.getItemAsync("healthkit:consent:owner:sleep"),
    ).rejects.toThrow("Invalid SecureStore key");
  });

  it("round-trips and isolates consent and checkpoint state by account and installation", async () => {
    const consent = new HealthKitConsentStore();
    await consent.setEnabled("owner-a", "steps", true);
    await consent.setLookbackDays("owner-a", 45);
    expect(await consent.isEnabled("owner-b", "steps")).toBe(false);
    expect(await consent.getLookbackDays("owner-b")).toBe(30);

    const store = new SecureCheckpointStore();
    const keyA = checkpointKey("owner-a", "install-a", "steps");
    const keyB = checkpointKey("owner-b", "install-a", "steps");
    const saved = {
      ownerId: "owner-a",
      deviceInstallationId: "install-a",
      resourceType: "steps" as const,
      policyVersion: "healthkit-v1" as const,
      anchor: "opaque-anchor",
      savedAt: "2026-10-07T20:00:00Z",
    };
    await store.save(keyA, saved);
    expect(await store.load(keyA)).toEqual(saved);
    expect(await store.load(keyB)).toBeNull();
  });

  it("surfaces secure storage failures without claiming a checkpoint was saved", async () => {
    secureStoreMock.fail = true;
    const consent = new HealthKitConsentStore();
    const store = new SecureCheckpointStore();
    await expect(consent.setEnabled("owner-a", "steps", true)).rejects.toThrow(
      "SecureStore unavailable",
    );
    await expect(
      store.save(checkpointKey("owner-a", "install-a", "steps"), {
        ownerId: "owner-a",
        deviceInstallationId: "install-a",
        resourceType: "steps",
        policyVersion: "healthkit-v1",
        anchor: "opaque-anchor",
        savedAt: "2026-10-07T20:00:00Z",
      }),
    ).rejects.toThrow("SecureStore unavailable");
  });
});
