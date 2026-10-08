import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

export interface ProposalEditorBaseline {
  proposalId: string;
  revision: number;
}

export function ProposalEditor({
  proposalId,
  proposalRevision,
  baseline,
  rationale,
  commands,
  evidence,
  saving,
  onRationaleChange,
  onCommandsChange,
  onEvidenceChange,
  onSave,
  onCancel,
  onReplaceDraft,
}: {
  proposalId: string;
  proposalRevision: number;
  baseline: ProposalEditorBaseline | null;
  rationale: string;
  commands: string;
  evidence: string;
  saving: boolean;
  onRationaleChange: (value: string) => void;
  onCommandsChange: (value: string) => void;
  onEvidenceChange: (value: string) => void;
  onSave: () => void;
  onCancel: () => void;
  onReplaceDraft: () => void;
}) {
  return (
    <View style={styles.editor}>
      {baseline?.proposalId === proposalId &&
      baseline.revision !== proposalRevision ? (
        <View style={styles.errorCard}>
          <Text accessibilityRole="alert" style={styles.errorText}>
            This draft is based on revision {baseline.revision}; the current
            proposal is revision {proposalRevision}. Saving will be checked
            against the original revision and will conflict safely.
          </Text>
          <Button
            label="Review latest revision and replace my draft"
            onPress={onReplaceDraft}
          />
        </View>
      ) : null}
      <Field
        label="Evidence references"
        accessibilityLabel="Edit proposal evidence references"
        accessibilityHint="Use an empty array to remove evidence, or update object IDs and revisions after reviewing current records."
        value={evidence}
        onChange={onEvidenceChange}
        maxLength={8192}
        editor
      />
      <Field
        label="Rationale"
        accessibilityLabel="Edit proposal rationale"
        value={rationale}
        onChange={onRationaleChange}
        maxLength={1000}
      />
      <Text style={styles.fieldLabel}>Typed commands</Text>
      <Text style={styles.hint}>
        Edit the command objects as JSON. The server accepts only the supported
        typed actions and validates every field and owner reference before
        saving this new revision.
      </Text>
      <Field
        accessibilityLabel="Edit typed proposal commands"
        accessibilityHint="Commands are checked against the supported action schemas. Permission changes and delete actions are not accepted."
        value={commands}
        onChange={onCommandsChange}
        maxLength={65_536}
        editor
      />
      <Button
        label={saving ? "Saving…" : "Save new proposal revision"}
        disabled={saving}
        onPress={onSave}
      />
      <Button label="Cancel edit" disabled={saving} onPress={onCancel} />
    </View>
  );
}

function Field({
  label,
  accessibilityLabel,
  accessibilityHint,
  value,
  onChange,
  maxLength,
  editor = false,
}: {
  label?: string;
  accessibilityLabel: string;
  accessibilityHint?: string;
  value: string;
  onChange: (value: string) => void;
  maxLength: number;
  editor?: boolean;
}) {
  return (
    <View style={styles.field}>
      {label ? <Text style={styles.fieldLabel}>{label}</Text> : null}
      <TextInput
        accessibilityLabel={accessibilityLabel}
        accessibilityHint={accessibilityHint}
        value={value}
        onChangeText={onChange}
        maxLength={maxLength}
        multiline
        autoCapitalize="none"
        style={[styles.input, editor && styles.commandEditor]}
      />
    </View>
  );
}

function Button({
  label,
  onPress,
  disabled = false,
}: {
  label: string;
  onPress: () => void;
  disabled?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled, busy: disabled && label.endsWith("…") }}
      disabled={disabled}
      onPress={onPress}
      style={[styles.button, disabled && styles.disabled]}
    >
      <Text style={styles.buttonText}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  editor: { gap: 10 },
  field: { gap: 6 },
  fieldLabel: { color: "#203a2e", fontSize: 16, fontWeight: "700" },
  hint: { color: "#4d5a54", fontSize: 14, lineHeight: 20 },
  input: {
    backgroundColor: "#fff",
    borderColor: "#68786f",
    borderRadius: 10,
    borderWidth: 1,
    color: "#17201c",
    fontSize: 16,
    minHeight: 52,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  commandEditor: {
    minHeight: 240,
    textAlignVertical: "top",
    fontFamily: "monospace",
    fontSize: 13,
  },
  button: {
    alignItems: "center",
    backgroundColor: "#245d3a",
    borderRadius: 12,
    justifyContent: "center",
    minHeight: 50,
    paddingHorizontal: 18,
  },
  buttonText: { color: "#fff", fontSize: 16, fontWeight: "700" },
  disabled: { opacity: 0.55 },
  errorCard: {
    backgroundColor: "#fff",
    borderColor: "#9b1c1c",
    borderRadius: 14,
    borderWidth: 1,
    gap: 10,
    padding: 16,
  },
  errorText: { color: "#9b1c1c", fontSize: 15, lineHeight: 22 },
});
