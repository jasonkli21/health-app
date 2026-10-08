import { describe, expect, it } from "vitest";
import {
  AssistantRequestOwnership,
  runOwnedAssistantRequest,
} from "../src/features/assistant/requestOwnership";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

describe("Assistant request ownership", () => {
  it("releases an invalidated search and protects a newer operation from its completion", async () => {
    const ownership = new AssistantRequestOwnership();
    const oldRequest = deferred<string>();
    const newRequest = deferred<string>();
    const busyChanges: boolean[] = [];
    const results: string[] = [];
    const errors: string[] = [];

    const oldSearch = runOwnedAssistantRequest({
      ownership,
      kind: "search",
      key: '["walk",["event"]]',
      request: () => oldRequest.promise,
      onSuccess: (result) => results.push(result),
      onError: (error) => errors.push(String(error)),
      onBusyChange: (busy) => busyChanges.push(busy),
    });
    expect(ownership.busy).toBe(true);

    expect(ownership.changeKey("search", '["sleep",["event"]]')).toBe(true);
    busyChanges.push(ownership.busy);
    const newSearch = runOwnedAssistantRequest({
      ownership,
      kind: "search",
      key: '["sleep",["event"]]',
      request: () => newRequest.promise,
      onSuccess: (result) => results.push(result),
      onError: (error) => errors.push(String(error)),
      onBusyChange: (busy) => busyChanges.push(busy),
    });

    oldRequest.resolve("stale result");
    await oldSearch;
    expect(results).toEqual([]);
    expect(ownership.busy).toBe(true);

    newRequest.resolve("current result");
    await newSearch;
    expect(results).toEqual(["current result"]);
    expect(errors).toEqual([]);
    expect(busyChanges).toEqual([true, false, true, false]);
    expect(ownership.busy).toBe(false);
  });

  it("ignores an invalidated search error without blocking the next search", async () => {
    const ownership = new AssistantRequestOwnership();
    const oldRequest = deferred<string>();
    const newRequest = deferred<string>();
    const errors: string[] = [];
    const busyChanges: boolean[] = [];

    const oldSearch = runOwnedAssistantRequest({
      ownership,
      kind: "search",
      key: "old-query",
      request: () => oldRequest.promise,
      onSuccess: () => undefined,
      onError: (error) => errors.push(String(error)),
      onBusyChange: (busy) => busyChanges.push(busy),
    });
    ownership.changeKey("search", "new-query");
    busyChanges.push(ownership.busy);
    const newSearch = runOwnedAssistantRequest({
      ownership,
      kind: "search",
      key: "new-query",
      request: () => newRequest.promise,
      onSuccess: () => undefined,
      onError: (error) => errors.push(String(error)),
      onBusyChange: (busy) => busyChanges.push(busy),
    });

    oldRequest.reject(new Error("stale error"));
    await oldSearch;
    expect(errors).toEqual([]);
    expect(ownership.busy).toBe(true);

    newRequest.resolve("done");
    await newSearch;
    expect(busyChanges).toEqual([true, false, true, false]);
    expect(ownership.busy).toBe(false);
  });

  it("releases stale preview busy state on blur without letting it clear a refocused request", async () => {
    const ownership = new AssistantRequestOwnership();
    const oldPreview = deferred<string>();
    const currentPreview = deferred<string>();
    const results: string[] = [];
    const busyChanges: boolean[] = [];

    const blurredRequest = runOwnedAssistantRequest({
      ownership,
      kind: "preview",
      key: "scope",
      request: () => oldPreview.promise,
      onSuccess: (result) => results.push(result),
      onError: () => undefined,
      onBusyChange: (busy) => busyChanges.push(busy),
    });
    ownership.focusChanged();
    busyChanges.push(ownership.busy);
    const refocusedRequest = runOwnedAssistantRequest({
      ownership,
      kind: "preview",
      key: "scope",
      request: () => currentPreview.promise,
      onSuccess: (result) => results.push(result),
      onError: () => undefined,
      onBusyChange: (busy) => busyChanges.push(busy),
    });

    oldPreview.resolve("stale preview");
    await blurredRequest;
    expect(results).toEqual([]);
    expect(ownership.busy).toBe(true);

    currentPreview.resolve("current preview");
    await refocusedRequest;
    expect(results).toEqual(["current preview"]);
    expect(busyChanges).toEqual([true, false, true, false]);
    expect(ownership.busy).toBe(false);
  });
});
