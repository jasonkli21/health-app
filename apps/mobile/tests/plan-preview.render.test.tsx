import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { create, type ReactTestRenderer } from "react-test-renderer";
import { expect, it, vi } from "vitest";

import type { PlanPreviewMetadata } from "../src/features/assistant/planPreviewSession";
import { sessionStore } from "../src/auth/sessionStore";

vi.mock("../src/auth/sessionStore", async (importOriginal) => {
  const original =
    await importOriginal<typeof import("../src/auth/sessionStore")>();
  return { ...original, sessionStore: new original.SessionStore("firebase") };
});

vi.mock("react-native", () => {
  type Props = Record<string, unknown>;
  const text = ({ children }: Props) =>
    React.createElement("span", null, children as React.ReactNode);
  return {
    Pressable: ({ children, accessibilityRole, onPress, disabled }: Props) =>
      React.createElement(
        "button",
        {
          type: "button",
          role: accessibilityRole as string,
          onClick: onPress,
          disabled,
        },
        children as React.ReactNode,
      ),
    StyleSheet: { create: (value: unknown) => value },
    Text: text,
    View: text,
  };
});

it("shows only metadata and a refusal action while keeping cold launch closed", async () => {
  const { PlanPreviewDetails, PlanPreviewPanel } = await import(
    "../src/features/assistant/components/PlanPreviewPanel"
  );
  const observe = vi.fn();
  const cold = renderToStaticMarkup(
    <PlanPreviewPanel observe={observe} selectionScope="first" />,
  );
  expect(cold).toEqual("");
  sessionStore.setSignedIn("fixture-owner", null);
  const panel = renderToStaticMarkup(
    <PlanPreviewPanel observe={observe} selectionScope="first" />,
  );
  expect(panel).toContain("Decline preview");
  expect(panel).toContain("AI responses are unavailable");
  expect(observe).not.toHaveBeenCalled();

  const markup = renderToStaticMarkup(
    <PlanPreviewDetails
      preview={{
        history_turns: 1,
        expires_at: new Date(Date.now() + 30_000).toISOString(),
        source_sensitivity: "restricted",
        destination: {
          application: "health",
          provider: "ChatGPT",
          model: "Synthetic model",
          runtime: "Synthetic runtime",
          recipient: "Synthetic recipient",
        },
      }}
    />,
  );
  for (const label of [
    "Health profile preferences",
    "record field",
    "Restricted",
    "Synthetic model",
    "Synthetic runtime",
    "Synthetic recipient",
    "Includes a Personal AI memory item",
    "Expires",
  ])
    expect(markup).toContain(label);
  expect(markup).not.toContain("fixture-owner");
});

function deferredPreview() {
  let resolve!: (value: PlanPreviewMetadata) => void;
  const promise = new Promise<PlanPreviewMetadata>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

it("clears mounted metadata and aborts late responses when preview selection changes", async () => {
  const { PlanPreviewPanel } = await import(
    "../src/features/assistant/components/PlanPreviewPanel"
  );
  sessionStore.setSignedIn("fixture-owner", null);
  const request = deferredPreview();
  const lateRequest = deferredPreview();
  const observeA = vi
    .fn()
    .mockReturnValueOnce(request.promise)
    .mockReturnValue(lateRequest.promise);
  const observeB = vi.fn();
  const value = (model: string): PlanPreviewMetadata => ({
    history_turns: 1,
    expires_at: new Date(Date.now() + 30_000).toISOString(),
    source_sensitivity: "restricted",
    destination: {
      application: "health",
      provider: "ChatGPT",
      model,
      runtime: "Fixture runtime",
      recipient: "Fixture recipient",
    },
  });
  let panel!: ReactTestRenderer;
  const show = (observe: typeof observeA, selectionScope = "selected-a") =>
    React.act(() =>
      panel.update(<PlanPreviewPanel {...{ observe, selectionScope }} />),
    );
  const review = () =>
    React.act(() => {
      const button = panel.root
        .findAllByType("button")
        .find((candidate) =>
          candidate
            .findAllByType("span")
            .some((label) => label.props.children === "Review preview"),
        );
      expect(button).toBeDefined();
      button?.props.onClick();
    });
  const displayed = () => JSON.stringify(panel.toJSON());

  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  vi.useFakeTimers();
  try {
    await React.act(() => {
      panel = create(
        <PlanPreviewPanel observe={observeA} selectionScope="selected-a" />,
      );
    });
    await review();
    await React.act(() => request.resolve(value("Earlier fixture model")));
    expect(displayed()).toContain("Earlier fixture model");

    await show(observeB);
    expect(displayed()).not.toContain("Earlier fixture model");
    await show(observeA);
    expect(displayed()).not.toContain("Earlier fixture model");
    expect(observeA).toHaveBeenCalledTimes(1);
    expect(observeB).not.toHaveBeenCalled();

    await review();
    const signal = observeA.mock.calls[1]?.[0] as AbortSignal;
    await show(observeA, "selected-b");
    expect(signal.aborted).toBe(true);
    await show(observeA);
    await React.act(() => lateRequest.resolve(value("Late fixture model")));
    expect(displayed()).not.toContain("Late fixture model");
    expect(observeA).toHaveBeenCalledTimes(2);

    observeA.mockResolvedValueOnce(value("Current fixture model"));
    await review();
    expect(displayed()).toContain("Current fixture model");
    await show(observeA, "selected-b");
    await show(observeA);
    expect(displayed()).not.toContain("Current fixture model");
  } finally {
    if (panel) await React.act(() => panel.unmount());
    vi.useRealTimers();
    vi.unstubAllGlobals();
  }
});
