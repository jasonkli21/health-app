import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("react-native", () => {
  type Props = Record<string, unknown>;
  const container = (tag: string) =>
    function NativeContainer({ children, ...props }: Props) {
      return React.createElement(
        tag,
        {
          "aria-label": props.accessibilityLabel,
          "aria-description": props.accessibilityHint,
          role:
            props.accessibilityRole === "header"
              ? "heading"
              : props.accessibilityRole,
        },
        children as React.ReactNode,
      );
    };
  return {
    Pressable: ({ children, ...props }: Props) =>
      React.createElement(
        "button",
        {
          type: "button",
          "aria-label": props.accessibilityLabel,
          "aria-description": props.accessibilityHint,
        },
        children as React.ReactNode,
      ),
    StyleSheet: { create: (styles: unknown) => styles },
    Text: container("span"),
    TextInput: (props: Props) =>
      React.createElement("textarea", {
        value: props.value,
        readOnly: true,
        "aria-label": props.accessibilityLabel,
        "aria-description": props.accessibilityHint,
      }),
    View: container("div"),
  };
});

describe("ProposalEditor accessible fields", () => {
  it("keeps visible labels, input order, and accessibility purposes aligned", async () => {
    const { ProposalEditor } = await import(
      "../src/features/assistant/components/ProposalEditor"
    );
    const markup = renderToStaticMarkup(
      React.createElement(ProposalEditor, {
        proposalId: "proposal-1",
        proposalRevision: 2,
        baseline: { proposalId: "proposal-1", revision: 2 },
        rationale: "Reason",
        commands: "[]",
        evidence: "[]",
        saving: false,
        onRationaleChange: () => undefined,
        onCommandsChange: () => undefined,
        onEvidenceChange: () => undefined,
        onSave: () => undefined,
        onCancel: () => undefined,
        onReplaceDraft: () => undefined,
      }),
    );

    const evidenceLabel = markup.indexOf("Evidence references");
    const evidenceInput = markup.indexOf(
      'aria-label="Edit proposal evidence references"',
    );
    const rationaleLabel = markup.indexOf("Rationale");
    const rationaleInput = markup.indexOf(
      'aria-label="Edit proposal rationale"',
    );
    expect(evidenceLabel).toBeGreaterThanOrEqual(0);
    expect(evidenceLabel).toBeLessThan(evidenceInput);
    expect(evidenceInput).toBeLessThan(rationaleLabel);
    expect(rationaleLabel).toBeLessThan(rationaleInput);
    expect(markup).toContain(
      'aria-description="Use an empty array to remove evidence, or update object IDs and revisions after reviewing current records."',
    );
  });
});
