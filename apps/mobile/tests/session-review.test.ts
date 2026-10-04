import { describe, expect, it, vi } from "vitest";
import { HealthApiClient } from "@personal-health/api-client";
import {
  createAuthenticatedFetch,
  SessionChangedError,
} from "../src/auth/authenticatedFetch";
import { SessionStore } from "../src/auth/sessionStore";

const base = "https://api.example.test";
const response = (status: number) => ({
  ok: status === 200,
  status,
  json: async () => ({}),
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

describe("session review regressions", () => {
  it.each([
    "auth/user-disabled",
    "auth/user-token-expired",
    "auth/invalid-user-token",
    "auth/invalid-refresh-token",
    "auth/user-not-found",
  ])("expires definitive refresh failure %s", async (code) => {
    const store = new SessionStore("firebase");
    store.setSignedIn("old", null);
    const token = vi.fn(async (refresh: boolean) => {
      if (refresh) throw { code };
      return "token";
    });
    const request = createAuthenticatedFetch(
      store,
      token,
      async () => response(401),
      undefined,
      base,
    );
    await expect(request(`${base}/profile`)).rejects.toThrow("Sign in");
    expect(store.getSnapshot().status).toBe("expired");
    expect(token.mock.calls).toEqual([[false], [true]]);
  });

  it("keeps network refresh errors recoverable", async () => {
    const store = new SessionStore("firebase");
    store.setSignedIn("old", null);
    const networkError = { code: "auth/network-request-failed" };
    let failed = true;
    const request = createAuthenticatedFetch(
      store,
      async (refresh) => {
        if (refresh && failed) throw networkError;
        return "token";
      },
      async () => response(failed ? 401 : 200),
      undefined,
      base,
    );
    await expect(request(`${base}/profile`)).rejects.toBe(networkError);
    expect(store.getSnapshot().status).toBe("signed_in");
    failed = false;
    expect((await request(`${base}/profile`)).status).toBe(200);
  });

  it("does not expire a new owner when an old token fails asynchronously", async () => {
    const store = new SessionStore("firebase");
    store.setSignedIn("old", null);
    const pending = deferred<string>();
    const request = createAuthenticatedFetch(
      store,
      () =>
        pending.promise.then(() => {
          throw { code: "auth/user-disabled" };
        }),
      async () => response(200),
      undefined,
      base,
    );
    const check = expect(request(`${base}/profile`)).rejects.toBeInstanceOf(
      SessionChangedError,
    );
    store.setSignedIn("new", null);
    pending.resolve("");
    await check;
    expect(store.getSnapshot().userId).toBe("new");
  });

  it.each([200, 403])(
    "actual generated client rejects owner switch while parsing %s JSON",
    async (status) => {
      const store = new SessionStore("firebase");
      store.setSignedIn("old", null);
      const body = deferred<unknown>();
      const started = deferred<void>();
      const request = createAuthenticatedFetch(
        store,
        async () => "token",
        async () => ({
          ok: status === 200,
          status,
          json: () => {
            started.resolve();
            return body.promise;
          },
        }),
        undefined,
        base,
      );
      const client = new HealthApiClient(base, request);
      const check = expect(client.listProfileItems()).rejects.toBeInstanceOf(
        SessionChangedError,
      );
      await started.promise;
      store.setSignedIn("new", null);
      body.resolve({ items: [{ id: "old-private" }] });
      await check;
    },
  );
});

it("expires once for concurrent rejected requests from one epoch", async () => {
  const store = new SessionStore("firebase");
  store.setSignedIn("old", null);
  const rejected = deferred<void>();
  let requests = 0;
  const cleanup = vi.fn(({ epoch, userId }) => {
    store.markExpired(epoch, userId);
  });
  const request = createAuthenticatedFetch(
    store,
    async () => "token",
    async () => {
      requests += 1;
      if (requests === 4) rejected.resolve();
      await rejected.promise;
      return response(401);
    },
    cleanup,
    base,
  );
  // Release the first responses together; each then refreshes independently.
  const first = request(`${base}/profile`);
  const second = request(`${base}/profile`);
  await Promise.resolve();
  await Promise.resolve();
  rejected.resolve();
  const results = await Promise.allSettled([first, second]);
  expect(results.every((result) => result.status === "rejected")).toBe(true);
  expect(cleanup).toHaveBeenCalledTimes(1);
  expect(store.getSnapshot().status).toBe("expired");
});
