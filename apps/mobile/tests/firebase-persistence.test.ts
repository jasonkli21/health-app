import { describe, expect, it, vi } from "vitest";

import {
  createSecurePersistence,
  secureStorageKey,
} from "../src/auth/firebaseSession";
// The installed SDK's React Native entry exercises its real persistence class.
// @ts-expect-error Firebase does not publish declarations for this conditional entry.
import { getReactNativePersistence } from "../node_modules/@firebase/auth/dist/rn/index.js";

vi.mock("expo-secure-store", () => ({
  getItemAsync: vi.fn(),
  setItemAsync: vi.fn(),
  deleteItemAsync: vi.fn(),
}));

describe("Firebase SecureStore adapter", () => {
  it("round trips SDK user persistence with legal, distinct native keys", async () => {
    const native = new Map<string, string>();
    const valid = /^[A-Za-z0-9._-]+$/;
    const storage = createSecurePersistence({
      getItemAsync: async (key: string) => {
        expect(key).toMatch(valid);
        return native.get(key) ?? null;
      },
      setItemAsync: async (key: string, value: string) => {
        expect(key).toMatch(valid);
        native.set(key, value);
      },
      deleteItemAsync: async (key: string) => {
        expect(key).toMatch(valid);
        native.delete(key);
      },
    });
    const Persistence = getReactNativePersistence(storage);
    const persisted = new Persistence();
    const key = "firebase:authUser:API_KEY:[DEFAULT]";
    const collisionCandidate = "firebase_authUser_API_KEY__DEFAULT_";
    expect(secureStorageKey(key)).not.toBe(
      secureStorageKey(collisionCandidate),
    );
    expect(await persisted._isAvailable()).toBe(true);
    await persisted._set(key, { uid: "first-owner", token: "private" });
    expect(await new Persistence()._get(key)).toEqual({
      uid: "first-owner",
      token: "private",
    });
    await persisted._set(collisionCandidate, { uid: "second-owner" });
    await persisted._remove(key);
    expect(await new Persistence()._get(key)).toBeNull();
    expect(await new Persistence()._get(collisionCandidate)).toEqual({
      uid: "second-owner",
    });
  });
});
