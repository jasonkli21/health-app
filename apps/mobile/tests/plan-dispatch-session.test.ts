import { describe, expect, it, vi } from "vitest";

import { SessionStore } from "../src/auth/sessionStore";
import {
  DispatchObservationLifetime,
  validDispatchReview,
  type DispatchReview,
} from "../src/features/assistant/planDispatchSession";

const review = (): DispatchReview => ({
  originalKey: "00000000-0000-4000-8000-000000000003",
  category: "profile_preferences",
  fields: ["record"],
  preview: {
    history_turns: 1,
    source_sensitivity: "restricted",
    expires_at: new Date(Date.now() + 30_000).toISOString(),
    destination: {
      application: "health",
      model: "fake",
      provider: "fake",
      runtime: "fixture runtime",
      recipient: "fixture recipient",
    },
  },
});

describe("synthetic dispatch observation", () => {
  it("allows only the current restricted inventory and synthetic destination", () => {
    const value = review();
    expect(validDispatchReview(value)).toBe(true);
    value.preview.destination.provider = "other";
    expect(validDispatchReview(value)).toBe(false);
    value.preview.destination.provider = "fake";
    value.preview.expires_at = "2000-01-01T00:00:00Z";
    expect(validDispatchReview(value)).toBe(false);
  });

  it.each(["background", "screen switch", "logout", "owner switch", "reauth"])(
    "rejects an outstanding reply after %s",
    async (event) => {
      const store = new SessionStore("firebase");
      store.setSignedIn("first", null);
      const lifetime = new DispatchObservationLifetime(
        store,
        store.getSnapshot(),
      );
      lifetime.activate();
      let finish: (value: string) => void = () => undefined;
      const observe = vi.fn(
        () =>
          new Promise<string>((resolve) => {
            finish = resolve;
          }),
      );
      const pending = lifetime.run(observe);
      if (event === "background" || event === "screen switch") {
        lifetime.invalidate();
        expect(observe.mock.calls).toHaveLength(1);
        lifetime.activate();
      } else if (event === "logout") store.setSignedOut();
      else if (event === "owner switch") store.setSignedIn("second", null);
      else {
        store.setInitializing();
        store.setSignedIn("first", null);
      }
      finish("delayed synthetic result");
      expect(await pending).toBeNull();
    },
  );

  it("does not start in background, repeat a pending confirmation, or replay on foreground", async () => {
    const store = new SessionStore("firebase");
    store.setSignedIn("first", null);
    const lifetime = new DispatchObservationLifetime(
      store,
      store.getSnapshot(),
    );
    const confirm = vi.fn(async () => undefined);
    expect(await lifetime.run(confirm)).toBeNull();
    lifetime.activate();
    const sent = lifetime.run(confirm);
    expect(await lifetime.run(confirm)).toBeNull();
    expect(await sent).toEqual({ result: undefined });
    lifetime.invalidate();
    lifetime.activate();
    expect(confirm).toHaveBeenCalledTimes(1);
    const read = vi.fn(async () => "synthetic reply");
    expect(await lifetime.run(read)).toEqual({ result: "synthetic reply" });
    expect(confirm).toHaveBeenCalledTimes(1);
  });
});
