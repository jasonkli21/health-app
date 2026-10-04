import { beforeEach, describe, expect, it, vi } from "vitest";

const sdk = vi.hoisted(() => ({
  auth: { currentUser: null as null | { uid: string; email: string | null } },
  callbacks: [] as ((
    user: null | { uid: string; email: string | null },
  ) => void)[],
  signOut: vi.fn(),
  signIn: vi.fn(),
}));
vi.mock("firebase/app", () => ({
  getApps: () => [],
  initializeApp: () => ({}),
  getApp: () => ({}),
}));
vi.mock("expo-secure-store", () => ({}));
vi.mock("@firebase/auth", () => ({
  initializeAuth: () => sdk.auth,
  getReactNativePersistence: () => ({}),
  onAuthStateChanged: (
    _auth: unknown,
    callback: (user: null | { uid: string; email: string | null }) => void,
  ) => {
    sdk.callbacks.push(callback);
    return () => undefined;
  },
  signOut: () => sdk.signOut(),
  signInWithEmailAndPassword: () => sdk.signIn(),
}));

async function setup() {
  const firebase = await import("../src/auth/firebaseSession");
  const { sessionStore } = await import("../src/auth/sessionStore");
  firebase.startFirebaseSession();
  sdk.auth.currentUser = { uid: "old", email: null };
  sdk.callbacks.at(-1)!(sdk.auth.currentUser);
  return { firebase, store: sessionStore };
}

beforeEach(() => {
  vi.resetModules();
  vi.stubEnv("EXPO_PUBLIC_AUTH_MODE", "firebase");
  for (const key of ["API_KEY", "AUTH_DOMAIN", "PROJECT_ID", "APP_ID"])
    vi.stubEnv(`EXPO_PUBLIC_FIREBASE_${key}`, "configured");
  sdk.auth.currentUser = null;
  sdk.callbacks = [];
  sdk.signOut.mockReset().mockImplementation(async () => {
    sdk.auth.currentUser = null;
    sdk.callbacks.at(-1)!(null);
  });
  sdk.signIn.mockReset().mockImplementation(async () => {
    sdk.auth.currentUser = { uid: "new", email: null };
    sdk.callbacks.at(-1)!(sdk.auth.currentUser);
  });
});

describe("Firebase rejected session cleanup", () => {
  it("skips delayed old-owner cleanup after new sign-in and suppresses stale callbacks", async () => {
    const { firebase, store } = await setup();
    const epoch = store.getSnapshot().epoch;
    store.markExpired(epoch, "old");
    sdk.callbacks[0]!(sdk.auth.currentUser);
    expect(store.getSnapshot().status).toBe("expired");
    await firebase.signIn("new@example.test", "password");
    await firebase.clearRejectedFirebaseSession(epoch, "old");
    sdk.callbacks[0]!({ uid: "old", email: null });
    sdk.callbacks[0]!(null);
    expect(store.getSnapshot().userId).toBe("new");
    expect(sdk.signOut).not.toHaveBeenCalled();
  });

  it("concurrent rejections clean once; sign-in waits for in-progress SDK cleanup", async () => {
    const { firebase, store } = await setup();
    const epoch = store.getSnapshot().epoch;
    expect(store.markExpired(epoch, "old")).toBe(true);
    expect(store.markExpired(epoch, "old")).toBe(false);
    let finish!: () => void;
    sdk.signOut.mockImplementationOnce(
      () =>
        new Promise<void>((resolve) => {
          finish = () => {
            sdk.auth.currentUser = null;
            resolve();
          };
        }),
    );
    const cleanup = firebase.clearRejectedFirebaseSession(epoch, "old");
    const other = firebase.clearRejectedFirebaseSession(epoch, "old");
    await Promise.resolve();
    const signIn = firebase.signIn("new@example.test", "password");
    expect(sdk.signIn).not.toHaveBeenCalled();
    finish();
    await Promise.all([cleanup, other, signIn]);
    expect(sdk.signOut).toHaveBeenCalledTimes(1);
    expect(store.getSnapshot().userId).toBe("new");
  });

  it("ignores old listener generations after restarting", async () => {
    const { firebase, store } = await setup();
    firebase.startFirebaseSession();
    sdk.auth.currentUser = { uid: "new", email: null };
    sdk.callbacks[0]!(sdk.auth.currentUser);
    expect(store.getSnapshot().userId).toBe("old");
    sdk.callbacks[1]!(sdk.auth.currentUser);
    expect(store.getSnapshot().userId).toBe("new");
  });
});

it("ignores a stale sign-in completion after a newer sign-out intent", async () => {
  const { firebase, store } = await setup();
  let finish!: () => void;
  sdk.signIn.mockImplementationOnce(
    () =>
      new Promise<void>((resolve) => {
        finish = () => {
          sdk.auth.currentUser = { uid: "new", email: null };
          sdk.callbacks.at(-1)!(sdk.auth.currentUser);
          resolve();
        };
      }),
  );
  const signIn = firebase.signIn("new@example.test", "password");
  await Promise.resolve();
  const signOut = firebase.signOutCurrentUser();
  finish();
  await Promise.all([signIn, signOut]);
  expect(store.getSnapshot().status).toBe("signed_out");
  expect(sdk.auth.currentUser).toBeNull();
});
