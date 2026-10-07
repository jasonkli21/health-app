import { getApp, getApps, initializeApp } from "firebase/app";
import * as firebaseAuth from "@firebase/auth";
import type { Persistence, ReactNativeAsyncStorage } from "@firebase/auth";
import * as SecureStore from "expo-secure-store";

import { sessionStore } from "./sessionStore";

export function secureStorageKey(key: string): string {
  // Fixed-width UTF-16 code units give an injective mapping for all JS strings.
  return `firebase_${Array.from({ length: key.length }, (_, index) =>
    key.charCodeAt(index).toString(16).padStart(4, "0"),
  ).join("")}`;
}

export function createSecurePersistence(
  store: Pick<
    typeof SecureStore,
    "getItemAsync" | "setItemAsync" | "deleteItemAsync"
  >,
): ReactNativeAsyncStorage {
  return {
    getItem: (key) => store.getItemAsync(secureStorageKey(key)),
    setItem: (key, value) => store.setItemAsync(secureStorageKey(key), value),
    removeItem: (key) => store.deleteItemAsync(secureStorageKey(key)),
  };
}

const securePersistence = createSecurePersistence(SecureStore);

// Firebase's React Native package entry exports this API, while its top-level
// declaration file omits it. Metro selects the package's documented
// `react-native` export condition; keep this narrow assertion at that boundary.
const getReactNativePersistence = (
  firebaseAuth as typeof firebaseAuth & {
    getReactNativePersistence: (
      storage: ReactNativeAsyncStorage,
    ) => Persistence;
  }
).getReactNativePersistence;

const firebaseConfig = {
  apiKey: process.env.EXPO_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.EXPO_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.EXPO_PUBLIC_FIREBASE_PROJECT_ID,
  appId: process.env.EXPO_PUBLIC_FIREBASE_APP_ID,
};

function configured(): boolean {
  return Boolean(
    firebaseConfig.apiKey &&
      firebaseConfig.authDomain &&
      firebaseConfig.projectId &&
      firebaseConfig.appId,
  );
}

let auth: firebaseAuth.Auth | null = null;
let stopListening: (() => void) | null = null;
let mutations: Promise<void> = Promise.resolve();
let operation = 0;
let mutating = false;
let listenerGeneration = 0;

function mutate(action: () => Promise<void>): Promise<void> {
  const next = mutations.then(async () => {
    mutating = true;
    try {
      await action();
    } finally {
      mutating = false;
    }
  });
  mutations = next.catch(() => undefined);
  return next;
}

export function startFirebaseSession(): void {
  if (!configured()) {
    sessionStore.setUnavailable(
      "Firebase sign-in is not configured for this build.",
    );
    return;
  }
  try {
    const app = getApps().length ? getApp() : initializeApp(firebaseConfig);
    try {
      auth = firebaseAuth.initializeAuth(app, {
        persistence: getReactNativePersistence(securePersistence),
      });
    } catch (error) {
      if (
        !(error instanceof Error) ||
        !error.message.includes("already been initialized")
      )
        throw error;
      auth = firebaseAuth.getAuth(app);
    }
    stopListening?.();
    const generation = ++listenerGeneration;
    stopListening = firebaseAuth.onAuthStateChanged(
      auth,
      (user) => {
        if (generation !== listenerGeneration || mutating) return;
        if (user && auth?.currentUser !== user) return;
        if (
          user &&
          ["expired", "signed_out"].includes(sessionStore.getSnapshot().status)
        )
          return;
        if (user) sessionStore.setSignedIn(user.uid, user.email);
        else if (
          auth?.currentUser === null &&
          sessionStore.getSnapshot().status !== "expired"
        )
          sessionStore.setSignedOut();
      },
      () => {
        if (
          generation !== listenerGeneration ||
          mutating ||
          sessionStore.getSnapshot().status === "expired"
        )
          return;
        sessionStore.setUnavailable(
          "The saved sign-in session could not be restored. Check this device and try again.",
        );
      },
    );
  } catch {
    sessionStore.setUnavailable(
      "Firebase sign-in could not start. Check this build's authentication settings.",
    );
  }
}

export async function signIn(email: string, password: string): Promise<void> {
  if (!auth) throw new Error("Firebase sign-in is unavailable.");
  const requestedAuth = auth;
  const intent = ++operation;
  await mutate(async () => {
    if (intent !== operation) return;
    // Invalidate owner requests before the SDK can install a different user.
    sessionStore.setInitializing();
    try {
      await firebaseAuth.signInWithEmailAndPassword(
        requestedAuth,
        email.trim(),
        password,
      );
    } catch (error) {
      if (intent === operation) sessionStore.setSignedOut();
      throw error;
    }
    if (intent !== operation) return;
    const user = requestedAuth.currentUser;
    if (user) sessionStore.setSignedIn(user.uid, user.email);
  });
}

export async function signOutCurrentUser(): Promise<void> {
  const intent = ++operation;
  const requestedAuth = auth;
  const currentUser = requestedAuth?.currentUser;
  sessionStore.setInitializing();
  await mutate(async () => {
    if (intent !== operation) return;
    try {
      if (requestedAuth) await firebaseAuth.signOut(requestedAuth);
      if (intent === operation) sessionStore.setSignedOut();
    } catch {
      if (intent !== operation) return;
      if (currentUser)
        sessionStore.setSignedIn(
          currentUser.uid,
          currentUser.email,
          "Sign-out failed. Try again.",
        );
      else sessionStore.setUnavailable("Sign-out failed. Try again.");
    }
  });
}

export async function signOutCurrentUserForSession(
  epoch: number,
  userId: string | null,
): Promise<boolean> {
  const matches = () => {
    const snapshot = sessionStore.getSnapshot();
    return (
      snapshot.epoch === epoch &&
      snapshot.userId === userId &&
      (userId === null
        ? snapshot.mode === "dev" && snapshot.status === "ready"
        : snapshot.status === "signed_in")
    );
  };
  if (!matches()) return false;

  const requestedAuth = auth;
  if (userId !== null && requestedAuth?.currentUser?.uid !== userId)
    return false;
  const intent = ++operation;
  let signedOut = false;
  await mutate(async () => {
    if (
      intent !== operation ||
      !matches() ||
      (userId !== null && requestedAuth?.currentUser?.uid !== userId)
    )
      return;
    sessionStore.setInitializing();
    try {
      if (requestedAuth) await firebaseAuth.signOut(requestedAuth);
      if (intent === operation) {
        if (userId !== null && requestedAuth?.currentUser?.uid !== userId)
          return;
        sessionStore.setSignedOut();
        signedOut = true;
      }
    } catch {
      const currentUser = requestedAuth?.currentUser;
      if (
        intent === operation &&
        userId !== null &&
        currentUser?.uid === userId
      ) {
        sessionStore.setSignedIn(
          currentUser.uid,
          currentUser.email,
          "Sign-out failed. Try again.",
        );
      } else if (intent === operation && currentUser === null) {
        sessionStore.setUnavailable("Sign-out failed. Try again.");
      }
    }
  });
  return signedOut;
}

export async function clearRejectedFirebaseSession(
  epoch: number,
  userId: string,
): Promise<void> {
  const rejectedAuth = auth;
  await mutate(async () => {
    if (
      sessionStore.isRejectedSession(epoch) &&
      rejectedAuth?.currentUser?.uid === userId
    )
      await firebaseAuth.signOut(rejectedAuth);
  });
}

export async function getCurrentIdToken(
  forceRefresh: boolean,
): Promise<string> {
  const user = auth?.currentUser;
  if (!user) throw new Error("No Firebase session is active.");
  return user.getIdToken(forceRefresh);
}
