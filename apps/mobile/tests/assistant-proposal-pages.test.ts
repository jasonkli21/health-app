import { describe, expect, it } from "vitest";
import {
  ProposalPageCoordinator,
  runProposalPageLoad,
} from "../src/features/assistant/proposalPages";

interface Page {
  items: string[];
  next_cursor: string | null;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function harness() {
  const coordinator = new ProposalPageCoordinator();
  const requests: { filter: string; cursor: string | undefined }[] = [];
  const loading: boolean[] = [];
  const pages: string[] = [];
  const errors: (string | null)[] = [];
  let cursor: string | null = null;
  let dataGeneration = 0;

  function loadPage(
    append: boolean,
    load: (filter: string, cursor: string | undefined) => Promise<Page>,
  ) {
    return runProposalPageLoad({
      coordinator,
      append,
      dataGeneration,
      getDataGeneration: () => dataGeneration,
      load: (filter, nextCursor) => {
        requests.push({ filter, cursor: nextCursor });
        return load(filter, nextCursor);
      },
      onPage: (page, shouldAppend) => {
        if (!shouldAppend) pages.length = 0;
        pages.push(...page.items);
      },
      onLoading: (value) => loading.push(value),
      onErrorMessage: (value) => errors.push(value),
      onCursor: (value) => {
        cursor = value;
      },
      requestMessage: () => "request failed",
    });
  }

  return {
    coordinator,
    requests,
    loading,
    pages,
    errors,
    get cursor() {
      return cursor;
    },
    loadPage,
    changeDataGeneration() {
      dataGeneration += 1;
      coordinator.invalidate();
    },
  };
}

describe("Assistant proposal pagination", () => {
  it("settles the first page once and appends the explicit next cursor", async () => {
    const state = harness();
    const firstPage = deferred<Page>();
    const first = state.loadPage(false, () => firstPage.promise);
    expect(state.requests).toEqual([{ filter: "pending", cursor: undefined }]);
    expect(state.loading).toEqual([true]);

    firstPage.resolve({ items: ["proposal-1"], next_cursor: "cursor-2" });
    await first;
    expect(state.cursor).toBe("cursor-2");
    expect(state.pages).toEqual(["proposal-1"]);
    expect(state.loading).toEqual([true, false]);
    expect(state.requests).toHaveLength(1);

    const nextPage = deferred<Page>();
    const append = state.loadPage(true, () => nextPage.promise);
    expect(state.requests).toEqual([
      { filter: "pending", cursor: undefined },
      { filter: "pending", cursor: "cursor-2" },
    ]);
    nextPage.resolve({ items: ["proposal-2"], next_cursor: null });
    await append;
    expect(state.pages).toEqual(["proposal-1", "proposal-2"]);
    expect(state.cursor).toBeNull();
    expect(state.errors).toEqual([null, null]);
  });

  it("rejects old filter and focus responses while preserving the newer page", async () => {
    const state = harness();
    const oldFilter = deferred<Page>();
    const oldRequest = state.loadPage(false, () => oldFilter.promise);
    state.coordinator.setFilter("applied");

    const appliedPage = deferred<Page>();
    const appliedRequest = state.loadPage(false, () => appliedPage.promise);
    oldFilter.resolve({ items: ["stale-pending"], next_cursor: null });
    await oldRequest;
    expect(state.pages).toEqual([]);
    expect(state.loading).toEqual([true, true]);

    appliedPage.resolve({ items: ["applied-1"], next_cursor: "applied-2" });
    await appliedRequest;
    expect(state.pages).toEqual(["applied-1"]);
    expect(state.cursor).toBe("applied-2");

    state.coordinator.focus();
    const blurredPage = deferred<Page>();
    const blurredRequest = state.loadPage(false, () => blurredPage.promise);
    state.coordinator.blur();
    const focusedPage = deferred<Page>();
    const focusedRequest = state.loadPage(false, () => focusedPage.promise);
    blurredPage.resolve({ items: ["stale-after-blur"], next_cursor: null });
    await blurredRequest;
    expect(state.pages).toEqual(["applied-1"]);

    focusedPage.resolve({ items: ["focused-1"], next_cursor: null });
    await focusedRequest;
    expect(state.pages).toEqual(["focused-1"]);
    expect(state.requests.map(({ filter }) => filter)).toEqual([
      "pending",
      "applied",
      "applied",
      "applied",
    ]);
  });

  it("invalidates a page after proposal data changes", async () => {
    const state = harness();
    const stalePage = deferred<Page>();
    const staleRequest = state.loadPage(false, () => stalePage.promise);
    state.changeDataGeneration();
    stalePage.resolve({ items: ["stale"], next_cursor: null });
    await staleRequest;
    expect(state.pages).toEqual([]);
    expect(state.loading).toEqual([true]);
  });
});
