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
  ({ epoch, userId }) => {
    if (!sessionStore.markExpired(epoch, userId)) return;
    void import("./firebaseSession")
      .then((firebase) => firebase.clearRejectedFirebaseSession(epoch, userId))
      .catch(() => undefined);
  },
);
