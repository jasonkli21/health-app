import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";

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
    Pressable: ({ children, accessibilityRole }: Props) =>
      React.createElement(
        "button",
        { type: "button", role: accessibilityRole as string },
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
  const cold = renderToStaticMarkup(<PlanPreviewPanel observe={observe} />);
  expect(cold).toEqual("");
  sessionStore.setSignedIn("fixture-owner", null);
  const panel = renderToStaticMarkup(<PlanPreviewPanel observe={observe} />);
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
