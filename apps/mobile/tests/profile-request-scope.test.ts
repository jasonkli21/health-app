import { describe, expect, it, vi } from "vitest";

import {
  RequestScope,
  requestNextPage,
} from "../src/features/profile/requestScope";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function handlers(
  state: { busy: boolean; pages: string[]; error: unknown },
  prefix: string,
) {
  return {
    onStart: () => {
      state.busy = true;
      state.error = null;
    },
    onSuccess: (page: string) => state.pages.push(`${prefix}:${page}`),
    onError: (error: unknown) => {
      state.error = error;
    },
    onFinish: () => {
      state.busy = false;
    },
  };
}

describe("Profile paged requests", () => {
  it.each([
    ["category change", "overview:all", "overview:background"],
    ["refocus", "overview:all", "overview:all"],
    ["reload", "history:item-1:0", "history:item-1:1"],
    ["item switch", "history:item-1:0", "history:item-2:0"],
  ])(
    "ignores a pending page after %s",
    async (_reason, priorScope, nextScope) => {
      const scope = new RequestScope();
      const state = {
        busy: false,
        pages: [] as string[],
        error: null as unknown,
      };
      const latePage = deferred<string>();
      const oldToken = scope.start(priorScope);
      const oldRequest = requestNextPage(
        scope,
        oldToken,
        "cursor-1",
        () => latePage.promise,
        handlers(state, "old"),
      );
      expect(state.busy).toBe(true);

      scope.invalidate(oldToken);
      const newToken = scope.start(nextScope);
      state.busy = false;
      state.pages = [];
      const newRequest = requestNextPage(
        scope,
        newToken,
        "cursor-1",
        async () => "current page",
        handlers(state, "new"),
      );
      await newRequest;
      expect(state).toEqual({
        busy: false,
        pages: ["new:current page"],
        error: null,
      });

      latePage.resolve("stale page");
      await oldRequest;
      expect(state).toEqual({
        busy: false,
        pages: ["new:current page"],
        error: null,
      });
    },
  );

  it("ignores stale page errors and does not clear the new page busy state", async () => {
    const scope = new RequestScope();
    const state = {
      busy: false,
      pages: [] as string[],
      error: null as unknown,
    };
    const latePage = deferred<string>();
    const oldToken = scope.start("history:item-1:0");
    const oldRequest = requestNextPage(
      scope,
      oldToken,
      "revision-50",
      () => latePage.promise,
      handlers(state, "old"),
    );

    scope.start("history:item-2:0");
    latePage.reject(new Error("stale failure"));
    await oldRequest;
    expect(state.error).toBeNull();
    expect(state.busy).toBe(true);
  });

  it("allows only one request for a cursor in the active scope", async () => {
    const scope = new RequestScope();
    const token = scope.start("overview:all");
    const state = {
      busy: false,
      pages: [] as string[],
      error: null as unknown,
    };
    const pending = deferred<string>();
    const request = vi.fn(() => pending.promise);
    const first = requestNextPage(
      scope,
      token,
      "cursor-1",
      request,
      handlers(state, "page"),
    );
    await requestNextPage(
      scope,
      token,
      "cursor-1",
      request,
      handlers(state, "duplicate"),
    );

    expect(request).toHaveBeenCalledTimes(1);
    pending.resolve("once");
    await first;
    expect(state.pages).toEqual(["page:once"]);
    expect(state.busy).toBe(false);
  });

  it("ignores a page after the screen loses focus", async () => {
    const scope = new RequestScope();
    const token = scope.start("overview:all");
    const state = {
      busy: false,
      pages: [] as string[],
      error: null as unknown,
    };
    const pending = deferred<string>();
    const request = requestNextPage(
      scope,
      token,
      "cursor-1",
      () => pending.promise,
      handlers(state, "page"),
    );
    scope.invalidate(token);
    state.busy = false;
    pending.resolve("late");
    await request;

    expect(state).toEqual({ busy: false, pages: [], error: null });
  });
});
