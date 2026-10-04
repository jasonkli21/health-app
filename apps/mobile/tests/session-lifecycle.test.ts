import { describe, expect, it, vi } from "vitest";

import type { FetchLike } from "@personal-health/api-client";

import { clearOnSessionChange } from "../src/auth/cacheLifecycle";
import {
  createAuthenticatedFetch,
  SessionChangedError,
} from "../src/auth/authenticatedFetch";
import { SessionStore } from "../src/auth/sessionStore";

function response(status: number) {
  return { ok: status >= 200 && status < 300, status, json: async () => ({}) };
}

describe("Firebase mobile session lifecycle", () => {
  it("adds a bearer token only in Firebase mode without putting it in the URL", async () => {
    const store = new SessionStore("firebase");
    store.setSignedIn("owner-1", "owner@example.test");
    const fetcher: FetchLike = vi.fn(async () => response(200));
    const authed = createAuthenticatedFetch(
      store,
      async () => "id-token-secret",
      fetcher,
      undefined,
      "https://api.example.test",
    );

    await authed("https://api.example.test/profile?q=private", {
      method: "GET",
    });

    expect(fetcher).toHaveBeenCalledWith(
      "https://api.example.test/profile?q=private",
      { method: "GET", headers: { authorization: "Bearer id-token-secret" } },
    );
    expect(JSON.stringify(vi.mocked(fetcher).mock.calls[0]?.[0])).not.toContain(
      "id-token-secret",
    );
  });

  it("preserves JSON headers and retries a rejected token once with a forced refresh", async () => {
    const store = new SessionStore("firebase");
    store.setSignedIn("owner-1", null);
    const tokens: boolean[] = [];
    const calls: { url: string; init?: Parameters<FetchLike>[1] }[] = [];
    const fetcher: FetchLike = async (url, init) => {
      calls.push({ url, init });
      return response(calls.length === 1 ? 401 : 200);
    };
    const authed = createAuthenticatedFetch(
      store,
      async (force) => {
        tokens.push(force);
        return `token-${tokens.length}`;
      },
      fetcher,
      undefined,
      "https://api.example.test",
    );

    await authed("https://api.example.test/profile", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: "{}",
    });

    expect(tokens).toEqual([false, true]);
    expect(calls).toHaveLength(2);
    expect(calls[1]?.init?.headers).toEqual({
      "content-type": "application/json",
      authorization: "Bearer token-2",
    });
  });

  it("expires the session after the single refresh retry is rejected", async () => {
    const store = new SessionStore("firebase");
    store.setSignedIn("owner-1", null);
    const epoch = store.getSnapshot().epoch;
    const authed = createAuthenticatedFetch(
      store,
      async () => "bad-token",
      async () => response(401),
      undefined,
      "https://api.example.test",
    );

    await expect(
      authed("https://api.example.test/profile", { method: "GET" }),
    ).rejects.toMatchObject({ status: 401 });
    expect(store.getSnapshot()).toMatchObject({
      status: "expired",
      userId: null,
      epoch: epoch + 1,
    });
  });

  it("drops an in-flight response if the account changes before it returns", async () => {
    const store = new SessionStore("firebase");
    store.setSignedIn("owner-1", null);
    let finish!: (result: ReturnType<typeof response>) => void;
    let signalStarted!: () => void;
    const started = new Promise<void>((resolve) => {
      signalStarted = resolve;
    });
    const fetcher: FetchLike = () =>
      new Promise((resolve) => {
        finish = resolve;
        signalStarted();
      });
    const authed = createAuthenticatedFetch(
      store,
      async () => "owner-1-token",
      fetcher,
      undefined,
      "https://api.example.test",
    );
    const request = expect(
      authed("https://api.example.test/profile", { method: "GET" }),
    ).rejects.toBeInstanceOf(SessionChangedError);

    await started;
    store.setSignedIn("owner-2", null);
    finish(response(200));

    await request;
  });

  it("clears in-memory create recovery state whenever the session epoch changes", () => {
    const store = new SessionStore("firebase");
    const clear = vi.fn();
    const stop = clearOnSessionChange(store, [clear]);
    store.setSignedIn("owner-1", null);
    store.setSignedIn("owner-2", null);
    store.setSignedOut();
    expect(clear).toHaveBeenCalledTimes(3);
    stop();
    store.setSignedIn("owner-3", null);
    expect(clear).toHaveBeenCalledTimes(3);
  });

  it("leaves local development requests unauthenticated", async () => {
    const store = new SessionStore("dev");
    const fetcher: FetchLike = vi.fn(async () => response(200));
    const authed = createAuthenticatedFetch(
      store,
      async () => "unused",
      fetcher,
    );

    await authed("http://127.0.0.1:8000/profile", { method: "GET" });

    expect(fetcher).toHaveBeenCalledWith("http://127.0.0.1:8000/profile", {
      method: "GET",
    });
  });
});
