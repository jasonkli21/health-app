import { useState } from "react";
import {
  AccessibilityInfo,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from "react-native";

import { profileErrorMessage } from "../api";
import {
  buildProfileFields,
  EMPTY_PROFILE_DRAFT,
  PROFILE_CATEGORIES,
  PROFILE_UNITS,
  type BuiltProfileFields,
  type ProfileDraft,
  type ProfileKind,
  type ValueDraft,
} from "../model";

type ProfileFormProps = {
  initialDraft?: ProfileDraft;
  submitLabel: string;
  onCancel: () => void;
  onSubmit: (fields: BuiltProfileFields) => Promise<void>;
  onDraftChange?: (draft: ProfileDraft) => void;
  onRetryUncertain?: () => Promise<void>;
  onConflictReload?: () => void;
};

const VALUE_TYPES: { value: ValueDraft["type"]; label: string }[] = [
  { value: "unknown", label: "Unknown" },
  { value: "text", label: "Text" },
  { value: "boolean", label: "Yes / No" },
  { value: "number", label: "Number" },
  { value: "quantity", label: "Quantity" },
  { value: "text_list", label: "List" },
];

function valueDraftFor(type: ValueDraft["type"]): ValueDraft {
  switch (type) {
    case "unknown":
      return { type: "unknown" };
    case "text":
      return { type: "text", value: "" };
    case "boolean":
      return { type: "boolean", value: null };
    case "number":
      return { type: "number", value: "" };
    case "quantity":
      return { type: "quantity", value: "", unit: "" };
    case "text_list":
      return { type: "text_list", value: "" };
  }
}

function SelectionButton({
  label,
  selected,
  onPress,
}: {
  label: string;
  selected: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityState={{ checked: selected }}
      accessibilityLabel={label}
      onPress={onPress}
      style={[styles.choice, selected && styles.choiceSelected]}
    >
      <Text style={[styles.choiceText, selected && styles.choiceTextSelected]}>
        {label}
      </Text>
    </Pressable>
  );
}

export function ProfileForm({
  initialDraft = EMPTY_PROFILE_DRAFT,
  submitLabel,
  onCancel,
  onSubmit,
  onDraftChange,
  onRetryUncertain,
  onConflictReload,
}: ProfileFormProps) {
  const [draft, setDraft] = useState<ProfileDraft>(() => ({ ...initialDraft }));
  const [error, setError] = useState<string | null>(null);
  const [conflictDetected, setConflictDetected] = useState(false);
  const [saving, setSaving] = useState(false);

  function update(patch: Partial<ProfileDraft>) {
    const next = { ...draft, ...patch };
    setDraft(next);
    onDraftChange?.(next);
    setError(null);
  }

  function updateValue(patch: Partial<ValueDraft>) {
    const next = {
      ...draft,
      value: { ...draft.value, ...patch } as ValueDraft,
    };
    setDraft(next);
    onDraftChange?.(next);
    setError(null);
  }

  async function save() {
    const result = buildProfileFields(draft);
    if (!result.ok) {
      setError(result.error);
      AccessibilityInfo.announceForAccessibility(result.error);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSubmit(result.fields);
    } catch (requestError) {
      const message = profileErrorMessage(requestError);
      if (message.includes("changed after you opened it")) {
        setConflictDetected(true);
      }
      setError(message);
      AccessibilityInfo.announceForAccessibility(message);
    } finally {
      setSaving(false);
    }
  }

  async function retryUncertain() {
    if (!onRetryUncertain) return;
    setSaving(true);
    setError(null);
    try {
      await onRetryUncertain();
    } catch (requestError) {
      const message = profileErrorMessage(requestError);
      setError(message);
      AccessibilityInfo.announceForAccessibility(message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <ScrollView
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
      accessibilityLabel="Profile item form"
    >
      <Text accessibilityRole="header" style={styles.title}>
        Profile item
      </Text>
      <Text style={styles.intro}>
        Add only what you want to remember. Unknown is a valid value; nothing is
        assumed for you.
      </Text>

      <Text accessibilityRole="header" style={styles.sectionTitle}>
        Category
      </Text>
      <View style={styles.choices}>
        {PROFILE_CATEGORIES.map((category) => (
          <SelectionButton
            key={category.value}
            label={category.label}
            selected={draft.kind === category.kind}
            onPress={() => update({ kind: category.kind as ProfileKind })}
          />
        ))}
      </View>

      <TextInput
        accessibilityLabel="Profile item label"
        accessibilityHint="A short description shown in your Profile. Required, up to 120 characters."
        placeholder="For example, preferred name"
        value={draft.label}
        onChangeText={(label) => update({ label })}
        maxLength={120}
        autoCapitalize="sentences"
        style={styles.input}
      />
      <Text style={styles.hint}>
        Key: lowercase letters, numbers, and underscores only.
      </Text>
      <TextInput
        accessibilityLabel="Profile item key"
        accessibilityHint="A stable lowercase identifier. Required."
        placeholder="for_example_preferred_name"
        value={draft.key}
        onChangeText={(key) => update({ key })}
        maxLength={64}
        autoCapitalize="none"
        autoCorrect={false}
        style={styles.input}
      />

      <Text accessibilityRole="header" style={styles.sectionTitle}>
        Value
      </Text>
      <Text style={styles.hint}>
        Choose Unknown if you do not know or want to enter a value.
      </Text>
      <View accessibilityRole="radiogroup" style={styles.choices}>
        {VALUE_TYPES.map((option) => (
          <SelectionButton
            key={option.value}
            label={option.label}
            selected={draft.value.type === option.value}
            onPress={() => update({ value: valueDraftFor(option.value) })}
          />
        ))}
      </View>

      {draft.value.type === "text" && (
        <TextInput
          accessibilityLabel="Text value"
          value={draft.value.value}
          onChangeText={(value) => updateValue({ value })}
          placeholder="Enter a text value"
          maxLength={2000}
          autoCapitalize="sentences"
          multiline
          style={[styles.input, styles.multiline]}
        />
      )}
      {draft.value.type === "boolean" && (
        <View
          accessibilityLabel="Yes or no value"
          accessibilityRole="radiogroup"
          style={styles.choices}
        >
          {[
            { label: "Unknown", value: null },
            { label: "Yes", value: true },
            { label: "No", value: false },
          ].map((option) => (
            <SelectionButton
              key={option.label}
              label={option.label}
              selected={
                draft.value.type === "boolean" &&
                draft.value.value === option.value
              }
              onPress={() => updateValue({ value: option.value })}
            />
          ))}
        </View>
      )}
      {draft.value.type === "number" && (
        <TextInput
          accessibilityLabel="Number value"
          value={draft.value.value}
          onChangeText={(value) => updateValue({ value })}
          placeholder="Enter a number; zero is valid"
          keyboardType="numbers-and-punctuation"
          style={styles.input}
        />
      )}
      {draft.value.type === "quantity" && (
        <View>
          <TextInput
            accessibilityLabel="Quantity value"
            value={draft.value.value}
            onChangeText={(value) => updateValue({ value })}
            placeholder="Enter a number; zero is valid"
            keyboardType="numbers-and-punctuation"
            style={styles.input}
          />
          <Text style={styles.hint}>
            Choose one unit. Units are never assumed.
          </Text>
          <View accessibilityRole="radiogroup" style={styles.choices}>
            {PROFILE_UNITS.map((unit) => (
              <SelectionButton
                key={unit}
                label={unit}
                selected={
                  draft.value.type === "quantity" && draft.value.unit === unit
                }
                onPress={() => updateValue({ unit })}
              />
            ))}
          </View>
        </View>
      )}
      {draft.value.type === "text_list" && (
        <TextInput
          accessibilityLabel="List values"
          accessibilityHint="Enter one list item on each line. Empty lines are ignored."
          value={draft.value.value}
          onChangeText={(value) => updateValue({ value })}
          placeholder="One item per line"
          maxLength={10_000}
          autoCapitalize="sentences"
          multiline
          style={[styles.input, styles.multiline]}
        />
      )}

      <Text accessibilityRole="header" style={styles.sectionTitle}>
        Effective dates (optional)
      </Text>
      <Text style={styles.hint}>
        Include a timezone, such as 2026-10-03T12:00:00Z.
      </Text>
      <TextInput
        accessibilityLabel="Effective start date and time"
        accessibilityHint="Optional ISO 8601 date and time with timezone."
        placeholder="Start (optional)"
        value={draft.valid_from}
        onChangeText={(valid_from) => update({ valid_from })}
        autoCapitalize="none"
        style={styles.input}
      />
      <TextInput
        accessibilityLabel="Effective end date and time"
        accessibilityHint="Optional ISO 8601 date and time with timezone."
        placeholder="End (optional)"
        value={draft.valid_to}
        onChangeText={(valid_to) => update({ valid_to })}
        autoCapitalize="none"
        style={styles.input}
      />

      <Text accessibilityRole="header" style={styles.sectionTitle}>
        Notes (optional)
      </Text>
      <TextInput
        accessibilityLabel="Profile item notes"
        value={draft.notes}
        onChangeText={(notes) => update({ notes })}
        placeholder="Add a note for yourself"
        maxLength={4000}
        autoCapitalize="sentences"
        multiline
        style={[styles.input, styles.multiline]}
      />

      <Text accessibilityRole="header" style={styles.sectionTitle}>
        Permissions
      </Text>
      <Text style={styles.hint}>
        Both permissions are off unless you turn them on.
      </Text>
      <View style={styles.switchRow}>
        <Text style={styles.switchLabel}>Allow AI use of this item</Text>
        <Switch
          accessibilityLabel="Allow AI use of this Profile item"
          accessibilityHint="Off by default. Turn on only if you want to allow AI use."
          value={draft.ai_use_allowed}
          onValueChange={(ai_use_allowed) => update({ ai_use_allowed })}
        />
      </View>
      <View style={styles.switchRow}>
        <Text style={styles.switchLabel}>
          Allow use by other apps and health domains through Personal AI
        </Text>
        <Switch
          accessibilityLabel="Allow use by other apps and health domains through Personal AI"
          accessibilityHint="Off by default. Turn on only if you want other apps and health domains to use this item through Personal AI."
          value={draft.cross_domain_use_allowed}
          onValueChange={(cross_domain_use_allowed) =>
            update({ cross_domain_use_allowed })
          }
        />
      </View>

      {error ? (
        <View>
          <Text
            accessibilityRole="alert"
            accessibilityLiveRegion="polite"
            style={styles.error}
          >
            {error}
          </Text>
        </View>
      ) : null}

      {onConflictReload && conflictDetected ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Reload latest Profile version"
          onPress={onConflictReload}
          style={styles.secondaryButton}
        >
          <Text style={styles.secondaryButtonText}>Reload latest version</Text>
        </Pressable>
      ) : null}

      {onRetryUncertain ? (
        <View style={styles.recovery}>
          <Text style={styles.hint}>
            A previous save may have completed. Recover that result before
            submitting edited details.
          </Text>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Retry original Profile save"
            accessibilityState={{ disabled: saving, busy: saving }}
            onPress={() => void retryUncertain()}
            disabled={saving}
            style={[styles.secondaryButton, saving && styles.disabledButton]}
          >
            <Text style={styles.secondaryButtonText}>
              {saving ? "Checking original save…" : "Retry original save"}
            </Text>
          </Pressable>
        </View>
      ) : null}

      <View style={styles.actions}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Cancel Profile item changes"
          onPress={onCancel}
          disabled={saving}
          style={[styles.secondaryButton, saving && styles.disabledButton]}
        >
          <Text style={styles.secondaryButtonText}>Cancel</Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={submitLabel}
          accessibilityState={{ disabled: saving, busy: saving }}
          onPress={() => void save()}
          disabled={saving}
          style={[styles.primaryButton, saving && styles.disabledButton]}
        >
          <Text style={styles.primaryButtonText}>
            {saving ? "Saving…" : submitLabel}
          </Text>
        </Pressable>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { gap: 12, padding: 20, paddingBottom: 36 },
  title: { color: "#17201c", fontSize: 28, fontWeight: "700" },
  intro: { color: "#46534d", fontSize: 16, lineHeight: 23 },
  sectionTitle: {
    color: "#203a2e",
    fontSize: 19,
    fontWeight: "700",
    marginTop: 12,
  },
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
  multiline: { minHeight: 100, textAlignVertical: "top" },
  choices: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  choice: {
    alignItems: "center",
    backgroundColor: "#fff",
    borderColor: "#68786f",
    borderRadius: 24,
    borderWidth: 1,
    justifyContent: "center",
    minHeight: 48,
    minWidth: 64,
    paddingHorizontal: 16,
  },
  choiceSelected: {
    backgroundColor: "#dcefe4",
    borderColor: "#245d3a",
    borderWidth: 2,
  },
  choiceText: { color: "#24342b", fontSize: 15, fontWeight: "600" },
  choiceTextSelected: { color: "#17492b" },
  switchRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: 16,
    justifyContent: "space-between",
    minHeight: 56,
  },
  switchLabel: { color: "#24342b", flex: 1, fontSize: 16, lineHeight: 22 },
  error: { color: "#9b1c1c", fontSize: 16, lineHeight: 23, marginVertical: 8 },
  recovery: { gap: 8 },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: 12, marginTop: 16 },
  primaryButton: {
    alignItems: "center",
    backgroundColor: "#245d3a",
    borderRadius: 12,
    justifyContent: "center",
    minHeight: 52,
    paddingHorizontal: 20,
  },
  primaryButtonText: { color: "#fff", fontSize: 16, fontWeight: "700" },
  secondaryButton: {
    alignItems: "center",
    backgroundColor: "#fff",
    borderColor: "#52645a",
    borderRadius: 12,
    borderWidth: 1,
    justifyContent: "center",
    minHeight: 52,
    paddingHorizontal: 20,
  },
  secondaryButtonText: { color: "#24342b", fontSize: 16, fontWeight: "600" },
  disabledButton: { opacity: 0.55 },
});
