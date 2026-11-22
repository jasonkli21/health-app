import { describe, expect, it, vi } from "vitest";

import { SessionStore } from "../src/auth/sessionStore";
import {
  observeCurrentPlanPreview,
  type PlanPreviewMetadata,
} from "../src/features/assistant/planPreviewSession";

const metadata = (): PlanPreviewMetadata => ({
  history_turns: 1,
  source_sensitivity: "restricted",
  expires_at: new Date(Date.now() + 30_000).toISOString(),
  destination: {
    application: "health",
    provider: "ChatGPT",
    model: "Synthetic model",
    runtime: "Synthetic runtime",
    recipient: "Synthetic recipient",
  },
});

describe("read-only plan preview observation", () => {
  it("adopts only a current, unexpired result", async () => {
    const session = new SessionStore("firebase");
    session.setSignedIn("first", null);
    const signal = new AbortController().signal;
    const start = session.getSnapshot();
    const value = metadata();
    const extra = {
      ...value,
      ownerId: "unrelated",
      record: "outside the preview",
    };
    expect(
      await observeCurrentPlanPreview(
        session,
        start,
        async () => extra,
        signal,
      ),
    ).toEqual(value);
    expect(
      await observeCurrentPlanPreview(
        session,
        start,
        async () => value,
        signal,
      ),
    ).toEqual(value);
    expect(
      await observeCurrentPlanPreview(
        session,
        start,
        async () => ({ ...value, expires_at: "2000-01-01T00:00:00Z" }),
        signal,
      ),
    ).toBeNull();
    expect(
      await observeCurrentPlanPreview(
        session,
        start,
        async () => {
          throw new Error("offline");
        },
        signal,
      ),
    ).toBeNull();
  });

  it.each([
    "switch",
    "logout",
    "same-user reauthentication",
    "decline",
  ] as const)(
    "discards metadata if %s interrupts the request",
    async (event) => {
      const sessions = new SessionStore("firebase");
      const controller = new AbortController();
      sessions.setSignedIn("first", null);
      const pending = observeCurrentPlanPreview(
        sessions,
        sessions.getSnapshot(),
        async () => metadata(),
        controller.signal,
      );
      if (event === "switch") sessions.setSignedIn("second", null);
      if (event === "logout") sessions.setSignedOut();
      if (event === "same-user reauthentication") {
        sessions.setInitializing();
        sessions.setSignedIn("first", null);
      }
      if (event === "decline") controller.abort();
      expect(await pending).toBeNull();
    },
  );

  it("does not request a preview on cold launch without current Firebase authority", async () => {
    const sessions = new SessionStore("firebase");
    const load = vi.fn<() => Promise<PlanPreviewMetadata | null>>();
    const found = await observeCurrentPlanPreview(
      sessions,
      sessions.getSnapshot(),
      load,
      new AbortController().signal,
    );
    expect(found).toBeNull();
    expect(load).not.toHaveBeenCalled();
  });
});
