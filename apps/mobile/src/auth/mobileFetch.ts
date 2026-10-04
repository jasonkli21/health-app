import type { FetchLike } from "@personal-health/api-client";

import { createAuthenticatedFetch } from "./authenticatedFetch";
import { sessionStore } from "./sessionStore";

export const mobileFetch: FetchLike = createAuthenticatedFetch(
  sessionStore,
  async (forceRefresh) => {
    const firebase = await import("./firebaseSession");
    return firebase.getCurrentIdToken(forceRefresh);
  },
  globalThis.fetch as FetchLike,
  (epoch) => {
    sessionStore.markExpired(epoch);
    void import("./firebaseSession")
      .then((firebase) => firebase.clearRejectedFirebaseSession())
      .catch(() => undefined);
  },
);
