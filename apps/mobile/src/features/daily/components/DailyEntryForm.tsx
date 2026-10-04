import { useRef, useState } from "react";
import {
  AccessibilityInfo,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import type {
  DailyDomain,
  DailyItem,
  DailyCreateRequest,
  DailyDraft,
  EventRecord,
  ObservationRecord,
} from "../model";
import {
  buildDailyCreateRequest,
  buildDailyUpdateRecord,
  draftFromDailyItem,
  emptyDailyDraft,
  newDailyId,
} from "../model";

type Props = {
  domain: DailyDomain;
  initialItem?: DailyItem;
  initialDraft?: DailyDraft;
  submitLabel: string;
  onCancel: () => void;
  onCreate?: (request: DailyCreateRequest, draft: DailyDraft) => Promise<void>;
  onUpdate?: (record: EventRecord | ObservationRecord) => Promise<void>;
  onRetryUncertain?: () => Promise<void>;
  onConflictReload?: () => void;
};

function Choice({
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
      accessibilityLabel={label}
      accessibilityState={{ checked: selected }}
      onPress={onPress}
      style={[styles.choice, selected && styles.choiceSelected]}
    >
      <Text style={[styles.choiceText, selected && styles.choiceTextSelected]}>
        {label}
      </Text>
    </Pressable>
  );
}

function Field({
  label,
  value,
  onChange,
  hint,
  placeholder,
  keyboardType,
  multiline = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: string;
  placeholder?: string;
  keyboardType?: "default" | "numbers-and-punctuation";
  multiline?: boolean;
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      {hint ? <Text style={styles.hint}>{hint}</Text> : null}
      <TextInput
        accessibilityLabel={label}
        accessibilityHint={hint}
        value={value}
        onChangeText={onChange}
        placeholder={placeholder}
        keyboardType={keyboardType}
        autoCapitalize={keyboardType === "default" ? "sentences" : "none"}
        autoCorrect={false}
        multiline={multiline}
        style={[styles.input, multiline && styles.multiline]}
      />
    </View>
  );
}

export function DailyEntryForm({
  domain,
  initialItem,
  initialDraft,
  submitLabel,
  onCancel,
  onCreate,
  onUpdate,
  onRetryUncertain,
  onConflictReload,
}: Props) {
  const [draft, setDraft] = useState<DailyDraft>(() =>
    initialItem
      ? draftFromDailyItem(initialItem)
      : (initialDraft ?? emptyDailyDraft()),
  );
  const ids = useRef({
    event: initialItem?.object_type === "event" ? initialItem.id : newDailyId(),
    observation:
      initialItem?.object_type === "observation"
        ? initialItem.id
        : newDailyId(),
    secondObservation: newDailyId(),
  });
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [saving, setSaving] = useState(false);

  function update(patch: Partial<DailyDraft>) {
    setDraft((current) => ({ ...current, ...patch }));
    setError(null);
    setConflict(false);
  }

  function showBuildError(message: string) {
    setError(message);
    AccessibilityInfo.announceForAccessibility(message);
  }

  async function send(operation: () => Promise<void>) {
    setSaving(true);
    setError(null);
    try {
      await operation();
    } catch (requestError) {
      const message =
        requestError instanceof Error
          ? requestError.message
          : "The daily entry could not be saved. Check your connection and try again.";
      setError(message);
      if (
        typeof requestError === "object" &&
        requestError !== null &&
        "status" in requestError &&
        requestError.status === 409
      ) {
        setConflict(true);
      }
      AccessibilityInfo.announceForAccessibility(message);
    } finally {
      setSaving(false);
    }
  }

  async function save() {
    if (initialItem) {
      if (!onUpdate) return;
      const result = buildDailyUpdateRecord(initialItem, draft);
      if (!result.ok) {
        showBuildError(result.error);
        return;
      }
      await send(() => onUpdate(result.value));
      return;
    }
    if (!onCreate) return;
    const result = buildDailyCreateRequest(domain, draft, ids.current);
    if (!result.ok) {
      showBuildError(result.error);
      return;
    }
    await send(() => onCreate(result.value, draft));
  }

  async function retryOriginal() {
    if (!onRetryUncertain) return;
    setSaving(true);
    setError(null);
    try {
      await onRetryUncertain();
    } catch (requestError) {
      const message =
        requestError instanceof Error
          ? requestError.message
          : "The original save could not be recovered. Try again.";
      setError(message);
      AccessibilityInfo.announceForAccessibility(message);
    } finally {
      setSaving(false);
    }
  }

  const eventKind =
    initialItem?.object_type === "event"
      ? initialItem.event.payload.kind
      : null;
  const observationMetric =
    initialItem?.object_type === "observation"
      ? initialItem.observation.payload.value.metric
      : null;
  const severityOnly = observationMetric === "symptom_severity";

  return (
    <ScrollView
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
      accessibilityLabel="Daily entry form"
    >
      <Text accessibilityRole="header" style={styles.title}>
        {initialItem ? "Edit entry" : "Add entry"}
      </Text>
      <Text style={styles.intro}>
        Enter only what you know. Blank quantities stay unrecorded; zero is a
        value you can enter.
      </Text>

      {domain !== "sleep" && !severityOnly ? (
        <View>
          <Text style={styles.fieldLabel}>Time detail</Text>
          <View accessibilityRole="radiogroup" style={styles.choices}>
            <Choice
              label="Exact time"
              selected={draft.precision === "instant"}
              onPress={() => update({ precision: "instant" })}
            />
            <Choice
              label="Date only"
              selected={draft.precision === "date_only"}
              onPress={() => update({ precision: "date_only" })}
            />
          </View>
        </View>
      ) : null}

      {domain !== "sleep" || initialItem ? (
        draft.precision === "date_only" ? (
          <Field
            label="Local calendar date"
            hint="Enter the calendar date you recorded. No time is inferred."
            value={draft.localDate}
            onChange={(localDate) => update({ localDate })}
            placeholder="YYYY-MM-DD"
          />
        ) : (
          <Field
            label={domain === "sleep" ? "Sleep start time" : "Recorded time"}
            hint="Include Z for UTC or an explicit offset, such as 2026-05-01T09:00:00-07:00."
            value={draft.instant}
            onChange={(instant) => update({ instant })}
            placeholder="2026-05-01T16:00:00Z"
          />
        )
      ) : null}

      <Field
        label="IANA timezone"
        hint="Used to place this entry on a local day, for example America/Los_Angeles."
        value={draft.timezone}
        onChange={(timezone) => update({ timezone })}
        placeholder="America/Los_Angeles"
      />

      {severityOnly ? (
        <Field
          label="Severity score (0 to 10)"
          hint="0 is a recorded value. Leave it blank only when you are creating a new symptom without a severity."
          value={draft.severity}
          onChange={(severity) => update({ severity })}
          placeholder="Enter a score"
          keyboardType="numbers-and-punctuation"
        />
      ) : null}

      {domain === "nutrition" && !initialItem ? (
        <>
          <Field
            label="Meal label"
            value={draft.label}
            onChange={(label) => update({ label })}
            placeholder="For example, Lunch"
          />
          <Field
            label="Foods (optional)"
            hint="Separate foods with commas or new lines."
            value={draft.foods}
            onChange={(foods) => update({ foods })}
            placeholder="Food names"
            multiline
          />
          <Field
            label="Energy (optional)"
            hint="Leave blank if unknown. The unit is shown and can be changed."
            value={draft.energyValue}
            onChange={(energyValue) => update({ energyValue })}
            placeholder="No default value"
            keyboardType="numbers-and-punctuation"
          />
          <View accessibilityRole="radiogroup" style={styles.choices}>
            <Choice
              label="kcal"
              selected={draft.energyUnit === "kcal"}
              onPress={() => update({ energyUnit: "kcal" })}
            />
            <Choice
              label="kJ"
              selected={draft.energyUnit === "kJ"}
              onPress={() => update({ energyUnit: "kJ" })}
            />
          </View>
        </>
      ) : null}

      {domain === "exercise" && !initialItem ? (
        <>
          <Field
            label="Activity"
            value={draft.label}
            onChange={(label) => update({ label })}
            placeholder="For example, Walk"
          />
          <Field
            label="Reported duration (optional)"
            hint="Choose a quantity or enter an end time below. Do not enter both."
            value={draft.durationValue}
            onChange={(durationValue) => update({ durationValue })}
            placeholder="No default value"
            keyboardType="numbers-and-punctuation"
          />
          <View accessibilityRole="radiogroup" style={styles.choices}>
            <Choice
              label="minutes"
              selected={draft.durationUnit === "min"}
              onPress={() => update({ durationUnit: "min" })}
            />
            <Choice
              label="hours"
              selected={draft.durationUnit === "h"}
              onPress={() => update({ durationUnit: "h" })}
            />
          </View>
          {draft.precision === "instant" ? (
            <Field
              label="End time (optional)"
              hint="An exact interval can be split across local days by elapsed time."
              value={draft.endedAt}
              onChange={(endedAt) => update({ endedAt })}
              placeholder="2026-05-01T10:00:00-07:00"
            />
          ) : null}
          <Field
            label="Distance (optional)"
            hint="Leave blank if unknown."
            value={draft.distanceValue}
            onChange={(distanceValue) => update({ distanceValue })}
            placeholder="No default value"
            keyboardType="numbers-and-punctuation"
          />
          <View accessibilityRole="radiogroup" style={styles.choices}>
            {(["m", "km", "mi"] as const).map((unit) => (
              <Choice
                key={unit}
                label={unit}
                selected={draft.distanceUnit === unit}
                onPress={() => update({ distanceUnit: unit })}
              />
            ))}
          </View>
        </>
      ) : null}

      {domain === "sleep" && !initialItem ? (
        <>
          <Field
            label="Sleep start time"
            hint="Include Z for UTC or an explicit offset."
            value={draft.instant}
            onChange={(instant) => update({ instant })}
            placeholder="2026-05-01T22:00:00-07:00"
          />
          <Field
            label="Sleep end time"
            hint="Required. Overnight sleep is allocated across local days by elapsed time."
            value={draft.endedAt}
            onChange={(endedAt) => update({ endedAt })}
            placeholder="2026-05-02T06:00:00-07:00"
          />
          <Field
            label="Sleep quality (optional, 1 to 5)"
            value={draft.quality}
            onChange={(quality) => update({ quality })}
            placeholder="No default value"
            keyboardType="numbers-and-punctuation"
          />
        </>
      ) : null}

      {domain === "symptoms" && !initialItem ? (
        <>
          <Field
            label="Symptom"
            value={draft.label}
            onChange={(label) => update({ label })}
            placeholder="For example, Headache"
          />
          <Field
            label="Severity (optional, 0 to 10)"
            hint="Severity is saved as a linked Observation in the same transaction as this symptom."
            value={draft.severity}
            onChange={(severity) => update({ severity })}
            placeholder="Leave blank if unknown"
            keyboardType="numbers-and-punctuation"
          />
        </>
      ) : null}

      {domain === "measurements" && !initialItem ? (
        <>
          <Text style={styles.fieldLabel}>Measurement type</Text>
          <View accessibilityRole="radiogroup" style={styles.choices}>
            {[
              ["weight", "Weight"],
              ["temperature", "Temperature"],
              ["blood_pressure", "Blood pressure pair"],
              ["pulse", "Pulse"],
            ].map(([value, label]) => (
              <Choice
                key={value}
                label={label!}
                selected={draft.measurementMetric === value}
                onPress={() =>
                  update({
                    measurementMetric: value as DailyDraft["measurementMetric"],
                    measurementUnit:
                      value === "weight"
                        ? "kg"
                        : value === "temperature"
                          ? "C"
                          : value === "pulse"
                            ? "bpm"
                            : "mmHg",
                  })
                }
              />
            ))}
          </View>
          {draft.measurementMetric === "blood_pressure" ? (
            <>
              <Field
                label="Systolic pressure (mmHg)"
                value={draft.systolicValue}
                onChange={(systolicValue) => update({ systolicValue })}
                placeholder="No default value"
                keyboardType="numbers-and-punctuation"
              />
              <Field
                label="Diastolic pressure (mmHg)"
                value={draft.diastolicValue}
                onChange={(diastolicValue) => update({ diastolicValue })}
                placeholder="No default value"
                keyboardType="numbers-and-punctuation"
              />
            </>
          ) : (
            <>
              <Field
                label="Measurement value"
                value={draft.measurementValue}
                onChange={(measurementValue) => update({ measurementValue })}
                placeholder="Enter a value; zero is valid"
                keyboardType="numbers-and-punctuation"
              />
              {draft.measurementMetric === "weight" ? (
                <View accessibilityRole="radiogroup" style={styles.choices}>
                  <Choice
                    label="kg"
                    selected={draft.measurementUnit === "kg"}
                    onPress={() => update({ measurementUnit: "kg" })}
                  />
                  <Choice
                    label="lb"
                    selected={draft.measurementUnit === "lb"}
                    onPress={() => update({ measurementUnit: "lb" })}
                  />
                </View>
              ) : null}
              {draft.measurementMetric === "temperature" ? (
                <View accessibilityRole="radiogroup" style={styles.choices}>
                  <Choice
                    label="°C"
                    selected={draft.measurementUnit === "C"}
                    onPress={() => update({ measurementUnit: "C" })}
                  />
                  <Choice
                    label="°F"
                    selected={draft.measurementUnit === "F"}
                    onPress={() => update({ measurementUnit: "F" })}
                  />
                </View>
              ) : null}
              {draft.measurementMetric === "pulse" ? (
                <Text style={styles.hint}>Unit: beats per minute (bpm)</Text>
              ) : null}
            </>
          )}
        </>
      ) : null}

      {initialItem?.object_type === "event" && eventKind === "meal" ? (
        <>
          <Field
            label="Meal label"
            value={draft.label}
            onChange={(label) => update({ label })}
          />
          <Field
            label="Foods (optional)"
            value={draft.foods}
            onChange={(foods) => update({ foods })}
            multiline
          />
          <Field
            label="Energy (optional)"
            value={draft.energyValue}
            onChange={(energyValue) => update({ energyValue })}
            keyboardType="numbers-and-punctuation"
          />
          <View accessibilityRole="radiogroup" style={styles.choices}>
            <Choice
              label="kcal"
              selected={draft.energyUnit === "kcal"}
              onPress={() => update({ energyUnit: "kcal" })}
            />
            <Choice
              label="kJ"
              selected={draft.energyUnit === "kJ"}
              onPress={() => update({ energyUnit: "kJ" })}
            />
          </View>
        </>
      ) : null}

      {initialItem?.object_type === "event" && eventKind === "workout" ? (
        <>
          <Field
            label="Activity"
            value={draft.label}
            onChange={(label) => update({ label })}
          />
          <Field
            label="Reported duration (optional)"
            value={draft.durationValue}
            onChange={(durationValue) => update({ durationValue })}
            keyboardType="numbers-and-punctuation"
          />
          <View accessibilityRole="radiogroup" style={styles.choices}>
            <Choice
              label="minutes"
              selected={draft.durationUnit === "min"}
              onPress={() => update({ durationUnit: "min" })}
            />
            <Choice
              label="hours"
              selected={draft.durationUnit === "h"}
              onPress={() => update({ durationUnit: "h" })}
            />
          </View>
          {draft.precision === "instant" ? (
            <Field
              label="End time (optional)"
              value={draft.endedAt}
              onChange={(endedAt) => update({ endedAt })}
            />
          ) : null}
          <Field
            label="Distance (optional)"
            value={draft.distanceValue}
            onChange={(distanceValue) => update({ distanceValue })}
            keyboardType="numbers-and-punctuation"
          />
          <View accessibilityRole="radiogroup" style={styles.choices}>
            {(["m", "km", "mi"] as const).map((unit) => (
              <Choice
                key={unit}
                label={unit}
                selected={draft.distanceUnit === unit}
                onPress={() => update({ distanceUnit: unit })}
              />
            ))}
          </View>
        </>
      ) : null}

      {initialItem?.object_type === "event" && eventKind === "sleep" ? (
        <>
          <Field
            label="Sleep label"
            value={draft.label}
            onChange={(label) => update({ label })}
          />
          <Field
            label="Sleep end time"
            value={draft.endedAt}
            onChange={(endedAt) => update({ endedAt })}
          />
          <Field
            label="Sleep quality (optional, 1 to 5)"
            value={draft.quality}
            onChange={(quality) => update({ quality })}
            keyboardType="numbers-and-punctuation"
          />
        </>
      ) : null}

      {initialItem?.object_type === "event" && eventKind === "symptom" ? (
        <Field
          label="Symptom"
          value={draft.label}
          onChange={(label) => update({ label })}
        />
      ) : null}

      {initialItem?.object_type === "observation" && !severityOnly ? (
        <>
          <Field
            label="Measurement value"
            value={draft.measurementValue}
            onChange={(measurementValue) => update({ measurementValue })}
            keyboardType="numbers-and-punctuation"
          />
          {observationMetric === "weight" ? (
            <View accessibilityRole="radiogroup" style={styles.choices}>
              <Choice
                label="kg"
                selected={draft.measurementUnit === "kg"}
                onPress={() => update({ measurementUnit: "kg" })}
              />
              <Choice
                label="lb"
                selected={draft.measurementUnit === "lb"}
                onPress={() => update({ measurementUnit: "lb" })}
              />
            </View>
          ) : null}
          {observationMetric === "temperature" ? (
            <View accessibilityRole="radiogroup" style={styles.choices}>
              <Choice
                label="°C"
                selected={draft.measurementUnit === "C"}
                onPress={() => update({ measurementUnit: "C" })}
              />
              <Choice
                label="°F"
                selected={draft.measurementUnit === "F"}
                onPress={() => update({ measurementUnit: "F" })}
              />
            </View>
          ) : null}
          {observationMetric === "systolic_pressure" ||
          observationMetric === "diastolic_pressure" ? (
            <Text style={styles.hint}>Unit: mmHg</Text>
          ) : null}
          {observationMetric === "pulse" ? (
            <Text style={styles.hint}>Unit: bpm</Text>
          ) : null}
        </>
      ) : null}

      {!severityOnly ? (
        <Field
          label="Notes (optional)"
          value={draft.notes}
          onChange={(notes) => update({ notes })}
          placeholder="Notes for yourself"
          multiline
        />
      ) : null}

      {error ? (
        <Text
          accessibilityRole="alert"
          accessibilityLiveRegion="polite"
          style={styles.error}
        >
          {error}
        </Text>
      ) : null}

      {conflict && onConflictReload ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Reload latest entry"
          accessibilityState={{ disabled: saving }}
          disabled={saving}
          onPress={onConflictReload}
          style={[styles.secondaryButton, saving && styles.disabled]}
        >
          <Text style={styles.secondaryButtonText}>Reload latest entry</Text>
        </Pressable>
      ) : null}

      {onRetryUncertain ? (
        <View style={styles.recovery}>
          <Text style={styles.hint}>
            The previous save may have completed. Recover that exact entry
            before submitting edited details.
          </Text>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Retry original daily save"
            accessibilityState={{ disabled: saving, busy: saving }}
            disabled={saving}
            onPress={() => void retryOriginal()}
            style={[styles.secondaryButton, saving && styles.disabled]}
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
          accessibilityLabel="Cancel daily entry"
          accessibilityState={{ disabled: saving }}
          disabled={saving}
          onPress={onCancel}
          style={[styles.secondaryButton, saving && styles.disabled]}
        >
          <Text style={styles.secondaryButtonText}>Cancel</Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={submitLabel}
          accessibilityState={{ disabled: saving, busy: saving }}
          disabled={saving}
          onPress={() => void save()}
          style={[styles.primaryButton, saving && styles.disabled]}
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
  content: { gap: 14, padding: 20, paddingBottom: 40 },
  title: { color: "#17201c", fontSize: 28, fontWeight: "700" },
  intro: { color: "#46534d", fontSize: 16, lineHeight: 23 },
  field: { gap: 7 },
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
  multiline: { minHeight: 90, textAlignVertical: "top" },
  choices: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  choice: {
    alignItems: "center",
    backgroundColor: "#fff",
    borderColor: "#68786f",
    borderRadius: 22,
    borderWidth: 1,
    justifyContent: "center",
    minHeight: 48,
    paddingHorizontal: 15,
  },
  choiceSelected: {
    backgroundColor: "#dcefe4",
    borderColor: "#245d3a",
    borderWidth: 2,
  },
  choiceText: { color: "#24342b", fontSize: 15, fontWeight: "600" },
  choiceTextSelected: { color: "#17492b" },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: 12, marginTop: 8 },
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
  recovery: { gap: 8 },
  disabled: { opacity: 0.55 },
  error: { color: "#9b1c1c", fontSize: 16, lineHeight: 23 },
});
