import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("react-native", () => {
  type Props = Record<string, unknown>;
  const text = ({ children, ...props }: Props) =>
    React.createElement(
      "span",
      { "aria-label": props.accessibilityLabel },
      children as React.ReactNode,
    );
  return {
    ActivityIndicator: () => React.createElement("span", null, "Loading"),
    Pressable: ({ children, accessibilityLabel, onPress }: Props) =>
      React.createElement(
        "button",
        { type: "button", "aria-label": accessibilityLabel, onClick: onPress },
        children as React.ReactNode,
      ),
    StyleSheet: { create: (styles: unknown) => styles },
    Text: text,
    View: text,
  };
});

describe("Shopping project picker", () => {
  it("renders the destination label and revision as the user choice", async () => {
    const { ShoppingProjectPicker } = await import(
      "../src/features/profile/components/ShoppingProjectPicker"
    );
    const markup = renderToStaticMarkup(
      React.createElement(ShoppingProjectPicker, {
        choices: [
          {
            project_id: "00000000-0000-0000-0000-000000000001",
            label: "Ergonomic chair",
            revision: 3,
          },
        ],
        selectedId: "",
        disabled: false,
        onSelect: () => undefined,
      }),
    );

    expect(markup).toContain("Select: Ergonomic chair (revision 3)");
    expect(markup).not.toContain("Shopping project ID");
    expect(markup).not.toContain("Current project revision");
  });
});
