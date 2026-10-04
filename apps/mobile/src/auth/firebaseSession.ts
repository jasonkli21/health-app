import { getApp, getApps, initializeApp } from "firebase/app";
import * as firebaseAuth from "@firebase/auth";
import type { Persistence, ReactNativeAsyncStorage } from "@firebase/auth";
import * as SecureStore from "expo-secure-store";

import { sessionStore } from "./sessionStore";

const securePersistence = {
  getItem: (key: string) => SecureStore.getItemAsync(key),
  setItem: (key: string, value: string) => SecureStore.setItemAsync(key, value),
  removeItem: (key: string) => SecureStore.deleteItemAsync(key),
};

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
    stopListening = firebaseAuth.onAuthStateChanged(
      auth,
      (user) => {
        if (user) sessionStore.setSignedIn(user.uid, user.email);
        else sessionStore.setSignedOut();
      },
      () => {
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
  await firebaseAuth.signInWithEmailAndPassword(auth, email.trim(), password);
}

export async function signOutCurrentUser(): Promise<void> {
  if (!auth) {
    sessionStore.setSignedOut();
    return;
  }
  const currentUser = auth.currentUser;
  sessionStore.setInitializing();
  try {
    await firebaseAuth.signOut(auth);
    sessionStore.setSignedOut();
  } catch {
    if (currentUser) {
      sessionStore.setSignedIn(
        currentUser.uid,
        currentUser.email,
        "Sign-out failed. Try again.",
      );
    } else {
      sessionStore.setUnavailable("Sign-out failed. Try again.");
    }
  }
}

export async function clearRejectedFirebaseSession(): Promise<void> {
  if (auth?.currentUser) await firebaseAuth.signOut(auth);
}

export async function getCurrentIdToken(
  forceRefresh: boolean,
): Promise<string> {
  const user = auth?.currentUser;
  if (!user) throw new Error("No Firebase session is active.");
  return user.getIdToken(forceRefresh);
}
