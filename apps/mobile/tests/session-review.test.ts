import { describe, expect, it, vi } from "vitest";
import { HealthApiClient } from "@personal-health/api-client";
import {
  createAuthenticatedFetch,
  SessionChangedError,
} from "../src/auth/authenticatedFetch";
import { SessionStore } from "../src/auth/sessionStore";
import { ApiError } from "@personal-health/api-client";

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
  it("preserves a recent-authentication error without refreshing or expiring the session", async () => {
    const store = new SessionStore("firebase");
    store.setSignedIn("owner-a", null);
    const token = vi.fn(async () => "token");
    const fetcher = vi.fn(async () => ({
      ok: false,
      status: 401,
      json: async () => ({
        code: "recent_authentication_required",
        message: "Sign in again.",
        request_id: "request-1",
      }),
    }));
    const request = createAuthenticatedFetch(
      store,
      token,
      fetcher,
      undefined,
      base,
    );

    const error = await request(`${base}/deletion-requests`).catch(
      (caught: unknown) => caught,
    );

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).body?.code).toBe(
      "recent_authentication_required",
    );
    expect(token).toHaveBeenCalledTimes(1);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(store.getSnapshot().status).toBe("signed_in");
  });

  it("preserves recent-auth errors after token refresh without losing the session", async () => {
    const store = new SessionStore("firebase");
    store.setSignedIn("owner-a", null);
    let sends = 0;
    const fetcher = vi.fn(async () => {
      sends += 1;
      return {
        ok: false,
        status: 401,
        json: async () =>
          sends === 1
            ? {
                code: "invalid_token",
                message: "Refresh token.",
                request_id: "request-1",
              }
            : {
                code: "recent_authentication_required",
                message: "Sign in again.",
                request_id: "request-1",
              },
      };
    });
    const token = vi.fn(async () => "token");
    const request = createAuthenticatedFetch(
      store,
      token,
      fetcher,
      undefined,
      base,
    );

    const error = await request(`${base}/deletion-requests`).catch(
      (caught: unknown) => caught,
    );

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).body?.request_id).toBe("request-1");
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(token).toHaveBeenCalledTimes(2);
    expect(store.getSnapshot().status).toBe("signed_in");
  });

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

  it("retains the invalid-token body after a failed refresh and expires that session", async () => {
    const store = new SessionStore("firebase");
    store.setSignedIn("owner-a", null);
    const request = createAuthenticatedFetch(
      store,
      async (refresh) => {
        if (refresh) return "refreshed-token";
        return "stale-token";
      },
      async () => ({
        ok: false,
        status: 401,
        json: async () => ({
          code: "invalid_token",
          message: "Token is invalid.",
          request_id: "request-2",
        }),
      }),
      undefined,
      base,
    );

    const error = await request(`${base}/profile`).catch(
      (caught: unknown) => caught,
    );

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).body?.code).toBe("invalid_token");
    expect(store.getSnapshot().status).toBe("expired");
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
