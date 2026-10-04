import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("react-native", () => {
  type Props = Record<string, unknown>;
  const aria = (props: Props) => ({
    "aria-label": props.accessibilityLabel,
    "aria-description": props.accessibilityHint,
    "aria-checked": (
      props.accessibilityState as { checked?: boolean } | undefined
    )?.checked,
    "aria-pressed": (
      props.accessibilityState as { selected?: boolean } | undefined
    )?.selected,
    role:
      props.accessibilityRole === "header"
        ? "heading"
        : props.accessibilityRole,
  });
  const container = (tag: string) =>
    function NativeContainer({
      children,
      accessibilityRole,
      accessibilityLabel,
      accessibilityHint,
      accessibilityState,
      ...props
    }: Props) {
      return React.createElement(
        tag,
        {
          ...aria({
            accessibilityRole,
            accessibilityLabel,
            accessibilityHint,
            accessibilityState,
          }),
        },
        children as React.ReactNode,
      );
    };
  return {
    AccessibilityInfo: { announceForAccessibility: vi.fn() },
    ActivityIndicator: () => React.createElement("span", null, "Loading"),
    Pressable: ({
      children,
      onPress,
      accessibilityRole,
      accessibilityLabel,
      accessibilityHint,
      accessibilityState,
    }: Props) =>
      React.createElement(
        "button",
        {
          type: "button",
          onClick: onPress,
          ...aria({
            accessibilityRole,
            accessibilityLabel,
            accessibilityHint,
            accessibilityState,
          }),
        },
        children as React.ReactNode,
      ),
    ScrollView: container("div"),
    StyleSheet: { create: (styles: unknown) => styles },
    Switch: ({ value, accessibilityLabel, accessibilityHint }: Props) =>
      React.createElement("input", {
        type: "checkbox",
        checked: value,
        readOnly: true,
        "aria-label": accessibilityLabel,
        "aria-description": accessibilityHint,
      }),
    Text: container("span"),
    TextInput: ({
      multiline,
      value,
      placeholder,
      maxLength,
      accessibilityLabel,
      accessibilityHint,
    }: Props) =>
      React.createElement(multiline ? "textarea" : "input", {
        value,
        placeholder,
        maxLength,
        readOnly: true,
        "aria-label": accessibilityLabel,
        "aria-description": accessibilityHint,
      }),
    View: container("div"),
  };
});

describe("ProfileForm accessible first render", () => {
  it("explains unknown values and keeps both use permissions off by default", async () => {
    const { ProfileForm } = await import(
      "../src/features/profile/components/ProfileForm"
    );
    const markup = renderToStaticMarkup(
      React.createElement(ProfileForm, {
        submitLabel: "Save Profile item",
        onCancel: () => undefined,
        onSubmit: async () => undefined,
      }),
    );
    expect(markup).toContain("Add only what you want to remember.");
    expect(markup).toContain("Unknown is a valid value");
    expect(markup).toContain('aria-label="Unknown"');
    expect(markup).toContain('aria-label="Allow AI use of this Profile item"');
    expect(markup).toContain(
      'aria-label="Allow cross-domain use of this Profile item"',
    );
    expect(markup).toContain("Save Profile item");
    expect(markup.match(/type="checkbox"/g)).toHaveLength(2);
    expect(markup).not.toMatch(/type="checkbox"[^>]*\schecked=/);
  });
});
