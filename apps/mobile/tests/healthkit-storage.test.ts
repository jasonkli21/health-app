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
  failOnKey: null as string | null,
}));

vi.mock("expo-secure-store", () => {
  const validateKey = (key: string) => {
    if (!/^[\w.-]+$/.test(key)) throw new Error("Invalid SecureStore key");
    secureStoreMock.keys.add(key);
  };
  return {
    getItemAsync: async (key: string) => {
      validateKey(key);
      if (secureStoreMock.fail || secureStoreMock.failOnKey === key)
        throw new Error("SecureStore unavailable");
      return secureStoreMock.values.get(key) ?? null;
    },
    setItemAsync: async (key: string, value: string) => {
      validateKey(key);
      if (secureStoreMock.fail || secureStoreMock.failOnKey === key)
        throw new Error("SecureStore unavailable");
      secureStoreMock.values.set(key, value);
    },
    deleteItemAsync: async (key: string) => {
      validateKey(key);
      if (secureStoreMock.fail || secureStoreMock.failOnKey === key)
        throw new Error("SecureStore unavailable");
      secureStoreMock.values.delete(key);
    },
  };
});

beforeEach(() => {
  secureStoreMock.values.clear();
  secureStoreMock.keys.clear();
  secureStoreMock.fail = false;
  secureStoreMock.failOnKey = null;
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

  it("clears realistic encoded identities without affecting another owner", async () => {
    const store = new SecureCheckpointStore();
    const ownerA = "a".repeat(28);
    const ownerB = "account-b";
    const installA = "12345678-1234-4234-8234-123456789abc";
    const installB = "install-b";
    const checkpoint = (ownerId: string, deviceInstallationId: string) => ({
      ownerId,
      deviceInstallationId,
      resourceType: "steps" as const,
      policyVersion: "healthkit-v1" as const,
      anchor: "opaque-anchor",
      savedAt: "2026-10-07T20:00:00Z",
    });
    const keyA = checkpointKey(ownerA, installA, "steps");
    const keyB = checkpointKey(ownerB, installB, "steps");

    expect(keyA.length).toBeGreaterThan(256);
    await store.save(keyA, checkpoint(ownerA, installA));
    await store.save(keyB, checkpoint(ownerB, installB));
    await store.save(keyB, {
      ...checkpoint(ownerB, installB),
      anchor: "updated",
    });
    await store.clearOwner(ownerA);

    expect(secureStoreMock.values.has(keyA)).toBe(false);
    expect(secureStoreMock.values.has(keyB)).toBe(true);
    expect(await store.load(keyB)).toMatchObject({
      ownerId: ownerB,
      anchor: "updated",
    });
    await store.clearOwner(ownerA);
    expect(secureStoreMock.values.has(keyB)).toBe(true);
  });

  it("preserves an invalid index and refuses to claim cleanup succeeded", async () => {
    const store = new SecureCheckpointStore();
    const ownerId = "owner-a";
    const key = checkpointKey(ownerId, "install-a", "steps");
    secureStoreMock.values.set(
      "healthkit.checkpoint.index.v1",
      JSON.stringify([key, 42]),
    );
    secureStoreMock.values.set(key, JSON.stringify({ ownerId }));

    await expect(store.clearOwner(ownerId)).rejects.toThrow(
      "Checkpoint index is invalid",
    );
    expect(secureStoreMock.values.has(key)).toBe(true);
    expect(secureStoreMock.values.get("healthkit.checkpoint.index.v1")).toBe(
      JSON.stringify([key, 42]),
    );
  });

  it("retains the old inventory when deletion is interrupted and completes on retry", async () => {
    const store = new SecureCheckpointStore();
    const ownerId = "owner-a";
    const key = checkpointKey(ownerId, "install-a", "steps");
    const checkpoint = {
      ownerId,
      deviceInstallationId: "install-a",
      resourceType: "steps" as const,
      policyVersion: "healthkit-v1" as const,
      anchor: "opaque-anchor",
      savedAt: "2026-10-07T20:00:00Z",
    };
    await store.save(key, checkpoint);

    secureStoreMock.failOnKey = key;
    await expect(store.clearOwner(ownerId)).rejects.toThrow(
      "SecureStore unavailable",
    );
    expect(
      JSON.parse(secureStoreMock.values.get("healthkit.checkpoint.index.v1")!),
    ).toEqual([key]);

    secureStoreMock.failOnKey = null;
    await store.clearOwner(ownerId);
    expect(secureStoreMock.values.has(key)).toBe(false);
    expect(secureStoreMock.values.get("healthkit.checkpoint.index.v1")).toBe(
      "[]",
    );
  });
});
