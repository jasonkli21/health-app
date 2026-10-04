import type { SessionStore } from "./sessionStore";

export function clearOnSessionChange(
  store: SessionStore,
  clearers: (() => void)[],
): () => void {
  let previousEpoch = store.getSnapshot().epoch;
  return store.subscribe(() => {
    const currentEpoch = store.getSnapshot().epoch;
    if (currentEpoch === previousEpoch) return;
    previousEpoch = currentEpoch;
    for (const clear of clearers) clear();
  });
}
