import { beforeEach, describe, expect, it, vi } from "vitest";

const hooks = vi.hoisted(() => {
  type HookSlot = { value: unknown; deps?: readonly unknown[] };
  const slots: HookSlot[] = [];
  let cursor = 0;
  let focused = false;
  let pendingFocus: (() => void | (() => void)) | null = null;
  let activeFocus: (() => void | (() => void)) | null = null;
  let focusCleanup: (() => void) | undefined;

  function sameDeps(
    left: readonly unknown[] | undefined,
    right: readonly unknown[],
  ) {
    return (
      left !== undefined &&
      left.length === right.length &&
      left.every((value, index) => Object.is(value, right[index]))
    );
  }

  function memo<T>(factory: () => T, deps: readonly unknown[]): T {
    const index = cursor++;
    const previous = slots[index];
    if (!previous || !sameDeps(previous.deps, deps)) {
      slots[index] = { value: factory(), deps };
    }
    return slots[index].value as T;
  }

  function commitFocus() {
    if (!focused || !pendingFocus || pendingFocus === activeFocus) return;
    focusCleanup?.();
    activeFocus = pendingFocus;
    const cleanup = activeFocus();
    focusCleanup = typeof cleanup === "function" ? cleanup : undefined;
  }

  return {
    react: {
      useCallback: <T extends (...args: never[]) => unknown>(
        callback: T,
        deps: readonly unknown[],
      ) => memo(() => callback, deps),
      useLayoutEffect: (effect: () => void, deps: readonly unknown[]) => {
        memo(() => {
          effect();
          return undefined;
        }, deps);
      },
      useMemo: memo,
      useReducer: (
        reducer: (state: unknown, action: unknown) => unknown,
        initial: unknown,
      ) => {
        const index = cursor++;
        if (!slots[index]) slots[index] = { value: initial };
        const slot = slots[index];
        return [
          slot.value,
          (action: unknown) => {
            slot.value = reducer(slot.value, action);
          },
        ];
      },
      useRef: (initial: unknown) => {
        const index = cursor++;
        if (!slots[index]) slots[index] = { value: { current: initial } };
        return slots[index].value;
      },
      useState: (initial: unknown) => {
        const index = cursor++;
        if (!slots[index]) {
          slots[index] = {
            value:
              typeof initial === "function"
                ? (initial as () => unknown)()
                : initial,
          };
        }
        const slot = slots[index];
        return [
          slot.value,
          (next: unknown) => {
            slot.value =
              typeof next === "function"
                ? (next as (current: unknown) => unknown)(slot.value)
                : next;
          },
        ];
      },
    },
    useFocusEffect: (callback: () => void | (() => void)) => {
      pendingFocus = callback;
    },
    reset: () => {
      slots.length = 0;
      cursor = 0;
      focused = false;
      pendingFocus = null;
      activeFocus = null;
      focusCleanup = undefined;
    },
    render: <T>(callback: () => T): T => {
      cursor = 0;
      const result = callback();
      commitFocus();
      return result;
    },
    focus: () => {
      focused = true;
      commitFocus();
    },
    blur: () => {
      focused = false;
      focusCleanup?.();
      focusCleanup = undefined;
      activeFocus = null;
    },
  };
});

const api = vi.hoisted(() => ({
  assistantApi: {
    getAssistantStatus: vi.fn(),
    previewAIContext: vi.fn(),
    searchAIEligibleHealthData: vi.fn(),
    sendAssistantMessage: vi.fn(),
    getActionProposal: vi.fn(),
    applyActionProposal: vi.fn(),
    rejectActionProposal: vi.fn(),
    editActionProposal: vi.fn(),
  },
  listActionProposals: vi.fn(),
  mergeProposalSummaries: (
    current: { id: string }[],
    incoming: { id: string }[],
  ) => {
    const byId = new Map(current.map((item) => [item.id, item]));
    for (const item of incoming) byId.set(item.id, item);
    return [...byId.values()];
  },
  editableProposalCommands: vi.fn(),
}));

vi.mock("react", () => hooks.react);
vi.mock("expo-router", () => ({ useFocusEffect: hooks.useFocusEffect }));
vi.mock("../src/features/assistant/api", () => api);

let useAssistantController: typeof import("../src/features/assistant/useAssistantController").useAssistantController;

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function renderController() {
  return hooks.render(() => useAssistantController());
}

function proposal(id: string) {
  return {
    id,
    revision: 1,
    updated_at: "2026-10-08T12:00:00Z",
  };
}

async function settleMicrotasks() {
  await Promise.resolve();
  await Promise.resolve();
}

beforeEach(async () => {
  hooks.reset();
  vi.clearAllMocks();
  api.assistantApi.getAssistantStatus.mockResolvedValue({ enabled: false });
  api.assistantApi.previewAIContext.mockResolvedValue({});
  api.listActionProposals.mockResolvedValue({ items: [], next_cursor: null });
  ({ useAssistantController } = await import(
    "../src/features/assistant/useAssistantController"
  ));
  hooks.focus();
});

describe("Assistant controller request wiring", () => {
  it("keeps focus initialization stable when the first page returns a cursor", async () => {
    const firstPage = deferred<{
      items: { id: string }[];
      next_cursor: string | null;
    }>();
    const nextPage = deferred<{
      items: { id: string }[];
      next_cursor: string | null;
    }>();
    api.listActionProposals
      .mockReturnValueOnce(firstPage.promise)
      .mockReturnValueOnce(nextPage.promise);

    let controller = renderController();
    expect(api.listActionProposals).toHaveBeenCalledTimes(1);
    expect(api.assistantApi.getAssistantStatus).toHaveBeenCalledTimes(1);

    controller.toggleResourceType("event", true);
    controller = renderController();
    await controller.previewContext();
    controller = renderController();
    expect(controller.previewIsCurrent).toBe(true);

    firstPage.resolve({
      items: [proposal("proposal-1")],
      next_cursor: "cursor-2",
    });
    await settleMicrotasks();
    controller = renderController();

    expect(api.listActionProposals).toHaveBeenCalledTimes(1);
    expect(api.assistantApi.getAssistantStatus).toHaveBeenCalledTimes(1);
    expect(controller.proposalCursor).toBe("cursor-2");
    expect(controller.previewIsCurrent).toBe(true);

    const append = controller.loadProposals(true);
    expect(api.listActionProposals).toHaveBeenLastCalledWith(
      "pending",
      "cursor-2",
    );
    nextPage.resolve({ items: [proposal("proposal-2")], next_cursor: null });
    await append;
    controller = renderController();

    expect(controller.proposals.map(({ id }) => id)).toEqual([
      "proposal-1",
      "proposal-2",
    ]);
    expect(api.listActionProposals).toHaveBeenCalledTimes(2);
    expect(api.assistantApi.getAssistantStatus).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["query edit", "stale success"],
    ["query edit", "stale error"],
    ["type change", "stale success"],
    ["type change", "stale error"],
  ] as const)(
    "releases search busy state on %s and preserves a newer request after %s",
    async (invalidation, oldOutcome) => {
      const oldSearch = deferred<{
        items: { object_id: string }[];
        next_cursor: null;
      }>();
      const currentSearch = deferred<{
        items: { object_id: string }[];
        next_cursor: null;
      }>();
      api.assistantApi.searchAIEligibleHealthData
        .mockReturnValueOnce(oldSearch.promise)
        .mockReturnValueOnce(currentSearch.promise);

      let controller = renderController();
      controller.toggleResourceType("event", true);
      controller = renderController();
      controller.changeSearchText("walk");
      controller = renderController();
      const oldRequest = controller.search();
      controller = renderController();
      expect(controller.busy).toBe(true);

      if (invalidation === "query edit") {
        controller.changeSearchText("sleep");
      } else {
        controller.toggleResourceType("observation", true);
      }
      controller = renderController();
      expect(controller.busy).toBe(false);
      const currentRequest = controller.search();
      controller = renderController();
      expect(controller.busy).toBe(true);

      if (oldOutcome === "stale success") {
        oldSearch.resolve({
          items: [{ object_id: "stale" }],
          next_cursor: null,
        });
      } else {
        oldSearch.reject(new Error("stale private error"));
      }
      await oldRequest;
      controller = renderController();
      expect(controller.busy).toBe(true);
      expect(controller.visibleSearchResults).toEqual([]);
      expect(controller.searchError).toBeNull();

      currentSearch.resolve({
        items: [{ object_id: "current" }],
        next_cursor: null,
      });
      await currentRequest;
      controller = renderController();
      expect(controller.busy).toBe(false);
      expect(
        controller.visibleSearchResults.map(({ object_id }) => object_id),
      ).toEqual(["current"]);
      expect(controller.searchError).toBeNull();
    },
  );

  it("rejects an in-flight search across blur and refocus", async () => {
    const oldSearch = deferred<{
      items: { object_id: string }[];
      next_cursor: null;
    }>();
    const currentSearch = deferred<{
      items: { object_id: string }[];
      next_cursor: null;
    }>();
    api.assistantApi.searchAIEligibleHealthData
      .mockReturnValueOnce(oldSearch.promise)
      .mockReturnValueOnce(currentSearch.promise);

    let controller = renderController();
    controller.toggleResourceType("event", true);
    controller = renderController();
    controller.changeSearchText("walk");
    controller = renderController();
    const oldRequest = controller.search();
    controller = renderController();
    expect(controller.busy).toBe(true);

    hooks.blur();
    controller = renderController();
    expect(controller.busy).toBe(false);
    hooks.focus();
    controller = renderController();

    const currentRequest = controller.search();
    controller = renderController();
    expect(controller.busy).toBe(true);
    oldSearch.resolve({ items: [{ object_id: "stale" }], next_cursor: null });
    await oldRequest;
    controller = renderController();
    expect(controller.busy).toBe(true);
    expect(controller.visibleSearchResults).toEqual([]);

    currentSearch.resolve({
      items: [{ object_id: "current" }],
      next_cursor: null,
    });
    await currentRequest;
    controller = renderController();
    expect(controller.busy).toBe(false);
    expect(
      controller.visibleSearchResults.map(({ object_id }) => object_id),
    ).toEqual(["current"]);
  });

  it("rejects an in-flight preview across blur and refocus", async () => {
    const oldPreview = deferred<{ marker: string }>();
    const currentPreview = deferred<{ marker: string }>();
    api.assistantApi.previewAIContext
      .mockReturnValueOnce(oldPreview.promise)
      .mockReturnValueOnce(currentPreview.promise);

    let controller = renderController();
    controller.toggleResourceType("event", true);
    controller = renderController();
    const oldRequest = controller.previewContext();
    controller = renderController();
    expect(controller.busy).toBe(true);

    hooks.blur();
    controller = renderController();
    expect(controller.busy).toBe(false);
    hooks.focus();
    controller = renderController();

    const currentRequest = controller.previewContext();
    controller = renderController();
    expect(controller.busy).toBe(true);
    oldPreview.resolve({ marker: "stale" });
    await oldRequest;
    controller = renderController();
    expect(controller.busy).toBe(true);
    expect(controller.pack).toBeNull();
    expect(controller.previewIsCurrent).toBe(false);

    currentPreview.resolve({ marker: "current" });
    await currentRequest;
    controller = renderController();
    expect(controller.busy).toBe(false);
    expect(controller.pack).toEqual({ marker: "current" });
    expect(controller.previewIsCurrent).toBe(true);
  });
});
