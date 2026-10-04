import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("react-native", () => {
  type Props = Record<string, unknown>;
  const attrs = (props: Props) => ({
    "aria-label": props.accessibilityLabel,
    "aria-description": props.accessibilityHint,
    "aria-checked": (
      props.accessibilityState as { checked?: boolean } | undefined
    )?.checked,
    role:
      props.accessibilityRole === "header"
        ? "heading"
        : props.accessibilityRole,
  });
  const container = (tag: string) =>
    function NativeContainer({ children, ...props }: Props) {
      return React.createElement(
        tag,
        attrs(props),
        children as React.ReactNode,
      );
    };
  return {
    AccessibilityInfo: { announceForAccessibility: vi.fn() },
    Pressable: ({ children, onPress, ...props }: Props) =>
      React.createElement(
        "button",
        { type: "button", onClick: onPress, ...attrs(props) },
        children as React.ReactNode,
      ),
    ScrollView: container("div"),
    StyleSheet: { create: (styles: unknown) => styles },
    Text: container("span"),
    TextInput: ({
      value,
      placeholder,
      accessibilityLabel,
      accessibilityHint,
    }: Props) =>
      React.createElement("input", {
        value,
        placeholder,
        readOnly: true,
        "aria-label": accessibilityLabel,
        "aria-description": accessibilityHint,
      }),
    View: container("div"),
  };
});

describe("DailyEntryForm first render", () => {
  it.each([
    ["nutrition", "Meal label"],
    ["exercise", "Activity"],
    ["sleep", "Sleep end time"],
    ["symptoms", "Severity (optional, 0 to 10)"],
    ["measurements", "Measurement value"],
  ] as const)("shows the %s form's labeled input", async (domain, label) => {
    const { DailyEntryForm } = await import(
      "../src/features/daily/components/DailyEntryForm"
    );
    const markup = renderToStaticMarkup(
      React.createElement(DailyEntryForm, {
        domain,
        submitLabel: "Save entry",
        onCancel: () => undefined,
        onCreate: async () => undefined,
      }),
    );
    expect(markup).toContain('aria-label="Daily entry form"');
    expect(markup).toContain(`aria-label="${label}"`);
    expect(markup).toContain('aria-label="Save entry"');
  });

  it("shows blank measurement inputs, explicit units, and the blood-pressure pair option", async () => {
    const { DailyEntryForm } = await import(
      "../src/features/daily/components/DailyEntryForm"
    );
    const markup = renderToStaticMarkup(
      React.createElement(DailyEntryForm, {
        domain: "measurements",
        submitLabel: "Save entry",
        onCancel: () => undefined,
        onCreate: async () => undefined,
      }),
    );
    expect(markup).toContain(
      "Blank quantities stay unrecorded; zero is a value you can enter.",
    );
    expect(markup).toContain('aria-label="Measurement value"');
    expect(markup).toContain("Blood pressure pair");
    expect(markup).toContain("kg");
    expect(markup).toContain("lb");
    expect(markup).toContain("IANA timezone");
    expect(markup).not.toMatch(/aria-label="Measurement value"[^>]*value="0"/);
  });

  it("makes linked symptom severity and retry controls accessible", async () => {
    const { DailyEntryForm } = await import(
      "../src/features/daily/components/DailyEntryForm"
    );
    const markup = renderToStaticMarkup(
      React.createElement(DailyEntryForm, {
        domain: "symptoms",
        submitLabel: "Save entry",
        onCancel: () => undefined,
        onCreate: async () => undefined,
        onRetryUncertain: async () => undefined,
      }),
    );
    expect(markup).toContain('aria-label="Severity (optional, 0 to 10)"');
    expect(markup).toContain("same transaction as this symptom");
    expect(markup).toContain('aria-label="Retry original daily save"');
    expect(markup).toContain("Date only");
  });
});
