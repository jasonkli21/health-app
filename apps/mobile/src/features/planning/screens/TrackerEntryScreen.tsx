import { useEffect, useMemo, useState } from "react";
import { useRouter } from "expo-router";
import {
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import type { components } from "@personal-health/api-client";
import { sessionStore } from "../../../auth/sessionStore";

import {
  activeTrackerCreateRecovery,
  planningApi,
  planningErrorMessage,
} from "../api";
import { collectTrackerValues, setTrackerInput } from "../trackerEntry";
import type { TrackerField, TrackerInputMap } from "../trackerEntry";
import {
  dailyApi,
  isDailyCreateAttemptCurrent,
  type DailyCreateAttempt,
} from "../../daily/api";
import {
  DEVICE_TIMEZONE,
  emptyDailyDraft,
  newDailyId,
} from "../../daily/model";
import {
  ActionButton,
  LoadingMessage,
  StatusMessage,
} from "../../profile/components/Ui";

type Tracker = components["schemas"]["TrackerResponse"];
type ValueMap = TrackerInputMap;

export default function TrackerEntryScreen() {
  const router = useRouter();
  const [trackers, setTrackers] = useState<Tracker[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [values, setValues] = useState<ValueMap>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nextTrackerCursor, setNextTrackerCursor] = useState<string | null>(
    null,
  );
  const [loadingMoreTrackers, setLoadingMoreTrackers] = useState(false);
  const [recoveryAttempt, setRecoveryAttempt] =
    useState<DailyCreateAttempt | null>(null);
  const selected =
    trackers.find((tracker) => tracker.id === selectedId) ?? null;
  const recovered = Boolean(
    recoveryAttempt && activeTrackerCreateRecovery.isUncertain,
  );

  useEffect(() => {
    let current = true;
    planningApi
      .listTrackers({ limit: 100 })
      .then((page) => {
        if (!current) return;
        const active = page.items.filter(
          (item): item is Tracker =>
            item.object_type === "tracker_definition" &&
            item.status === "active",
        );
        setTrackers(active);
        setNextTrackerCursor(page.next_cursor);
        const attempt = activeTrackerCreateRecovery.retryOriginal();
        const observation = attempt?.request.observations?.[0]?.observation;
        const custom = observation?.payload.value;
        if (attempt && custom?.metric === "custom") {
          setRecoveryAttempt(attempt);
          setSelectedId(custom.tracker_id);
        } else {
          setSelectedId(active[0]?.id ?? null);
        }
      })
      .catch((requestError: unknown) => {
        if (current) setError(planningErrorMessage(requestError));
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, []);

  async function loadMoreTrackers() {
    if (!nextTrackerCursor || loadingMoreTrackers) return;
    setLoadingMoreTrackers(true);
    setError(null);
    try {
      const page = await planningApi.listTrackers({
        limit: 100,
        cursor: nextTrackerCursor,
      });
      const active = page.items.filter(
        (item): item is Tracker =>
          item.object_type === "tracker_definition" && item.status === "active",
      );
      setTrackers((current) => [...current, ...active]);
      setNextTrackerCursor(page.next_cursor);
    } catch (requestError) {
      setError(planningErrorMessage(requestError));
    } finally {
      setLoadingMoreTrackers(false);
    }
  }

  const fields = useMemo(() => selected?.definition.fields ?? [], [selected]);

  function update(id: string, value: string | boolean | undefined) {
    setValues((current) => setTrackerInput(current, id, value));
  }

  async function submit() {
    setError(null);
    const sessionAtStart = sessionStore.getSnapshot();
    const isCurrentSession = () => {
      const latest = sessionStore.getSnapshot();
      return (
        latest.epoch === sessionAtStart.epoch &&
        latest.userId === sessionAtStart.userId
      );
    };
    if (!selected && !recoveryAttempt) {
      setError("Create a custom tracker before logging an entry.");
      return;
    }
    let attempt = recoveryAttempt;
    if (!attempt) {
      try {
        const customValues = collectTrackerValues(fields, values);
        const id = newDailyId();
        const request: components["schemas"]["DailyEntryCreateRequest"] = {
          events: [],
          observations: [
            {
              id,
              observation: {
                domain: selected!.definition.domain,
                time: {
                  precision: "instant",
                  occurred_at: new Date().toISOString(),
                  timezone: DEVICE_TIMEZONE,
                },
                interval_end: null,
                payload: {
                  value: {
                    metric: "custom",
                    unit: "custom",
                    tracker_id: selected!.id,
                    schema_version: selected!.current_schema_version,
                    values: customValues,
                  },
                },
                notes: null,
              },
            },
          ],
          links: [],
        };
        attempt = {
          request,
          primaryId: id,
          domain: selected!.definition.domain,
          draft: emptyDailyDraft(),
          sessionEpoch: sessionAtStart.epoch,
          sessionUserId: sessionAtStart.userId,
        };
        attempt = activeTrackerCreateRecovery.prepare(attempt);
      } catch (validationError) {
        setError(
          validationError instanceof Error
            ? validationError.message
            : "Check the tracker fields.",
        );
        return;
      }
    }
    if (!attempt) {
      setError(
        "Tracker entry could not be prepared. Check the fields and try again.",
      );
      return;
    }
    if (
      attempt.sessionEpoch !== undefined &&
      !isDailyCreateAttemptCurrent(attempt, sessionAtStart)
    ) {
      setError("This save belongs to a different session. Start a new entry.");
      return;
    }
    setBusy(true);
    try {
      const result = await dailyApi.createDailyEntry(attempt.request);
      if (!isCurrentSession()) return;
      activeTrackerCreateRecovery.resolve();
      setRecoveryAttempt(null);
      const entry = result.observations.find(
        (item) => item.id === attempt.primaryId,
      );
      if (entry) {
        router.replace({
          pathname: "/daily/item/[itemId]",
          params: { itemId: entry.id, type: "observation" },
        });
      } else {
        router.replace("/today");
      }
    } catch (requestError) {
      if (!isCurrentSession()) return;
      const uncertain = activeTrackerCreateRecovery.markFailure(
        attempt,
        requestError,
      );
      setRecoveryAttempt(uncertain ? attempt : null);
      setError(
        uncertain
          ? "The save result is uncertain. Retry the original tracker entry to recover it before changing fields."
          : planningErrorMessage(requestError),
      );
    } finally {
      if (isCurrentSession()) setBusy(false);
    }
  }

  if (loading) return <LoadingMessage label="Loading custom trackers" />;
  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text accessibilityRole="header" style={styles.title}>
          Log a tracker entry
        </Text>
        <Text style={styles.subtitle}>
          This creates an Observation using the selected immutable tracker
          schema.
        </Text>
        {error ? (
          <StatusMessage
            title="Could not save tracker entry"
            message={error}
            tone="error"
          />
        ) : null}
        {trackers.length === 0 && !recoveryAttempt ? (
          <View style={styles.empty}>
            <Text style={styles.cardTitle}>No active custom trackers</Text>
            <ActionButton
              label="Create a tracker"
              onPress={() =>
                router.push({
                  pathname: "/planning/new",
                  params: { kind: "tracker_definition" },
                })
              }
            />
          </View>
        ) : null}
        {trackers.length > 0 && !recoveryAttempt ? (
          <View style={styles.inputGroup}>
            <Text style={styles.inputLabel}>Tracker</Text>
            <View style={styles.choices}>
              {trackers.map((tracker) => (
                <Pressable
                  key={tracker.id}
                  accessibilityRole="button"
                  accessibilityState={{ selected: selectedId === tracker.id }}
                  onPress={() => {
                    setSelectedId(tracker.id);
                    setValues({});
                  }}
                  style={[
                    styles.choice,
                    selectedId === tracker.id && styles.choiceSelected,
                  ]}
                >
                  <Text
                    style={[
                      styles.choiceText,
                      selectedId === tracker.id && styles.choiceTextSelected,
                    ]}
                  >
                    {tracker.definition.name}
                  </Text>
                </Pressable>
              ))}
            </View>
          </View>
        ) : null}
        {nextTrackerCursor && !recoveryAttempt ? (
          <ActionButton
            label="Load more trackers"
            secondary
            busy={loadingMoreTrackers}
            onPress={() => void loadMoreTrackers()}
          />
        ) : null}
        {recoveryAttempt ? (
          <View style={styles.note}>
            <Text style={styles.noteText}>
              A previous tracker save may have completed. Retry its original ID
              and values before changing anything.
            </Text>
          </View>
        ) : (
          fields.map((field) => (
            <TrackerInput
              key={field.id}
              field={field}
              value={values[field.id]}
              onChange={(value) => update(field.id, value)}
              onClear={() => update(field.id, undefined)}
            />
          ))
        )}
        {selected ? (
          <Text style={styles.meta}>
            Schema version {selected.current_schema_version} ·{" "}
            {selected.definition.domain}
          </Text>
        ) : null}
        <ActionButton
          label={recovered ? "Retry original save" : "Save tracker entry"}
          busy={busy}
          disabled={!selected && !recoveryAttempt}
          onPress={() => void submit()}
        />
        <ActionButton
          label="Cancel"
          secondary
          disabled={busy}
          onPress={() => router.back()}
        />
      </ScrollView>
    </SafeAreaView>
  );
}

function TrackerInput({
  field,
  value,
  onChange,
  onClear,
}: {
  field: TrackerField;
  value: string | boolean | undefined;
  onChange: (value: string | boolean | undefined) => void;
  onClear: () => void;
}) {
  if (field.kind === "boolean") {
    const current = typeof value === "boolean" ? value : undefined;
    return (
      <View style={styles.inputGroup}>
        <Text style={styles.inputLabel}>
          {field.label}
          {field.required ? " · required" : ""}
        </Text>
        <View style={styles.choices}>
          {([true, false] as const).map((choice) => (
            <Pressable
              key={String(choice)}
              accessibilityRole="button"
              accessibilityState={{ selected: current === choice }}
              onPress={() => onChange(choice)}
              style={[
                styles.choice,
                current === choice && styles.choiceSelected,
              ]}
            >
              <Text
                style={[
                  styles.choiceText,
                  current === choice && styles.choiceTextSelected,
                ]}
              >
                {choice ? "Yes" : "No"}
              </Text>
            </Pressable>
          ))}
          {!field.required && current !== undefined ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={`Clear ${field.label}`}
              onPress={onClear}
              style={styles.choice}
            >
              <Text style={styles.choiceText}>Clear</Text>
            </Pressable>
          ) : null}
        </View>
      </View>
    );
  }
  if (field.kind === "enum") {
    const current = typeof value === "string" ? value : "";
    return (
      <View style={styles.inputGroup}>
        <Text style={styles.inputLabel}>
          {field.label}
          {field.required ? " · required" : ""}
        </Text>
        <View style={styles.choices}>
          {(field.choices ?? []).map((choice) => (
            <Pressable
              key={choice}
              accessibilityRole="button"
              accessibilityState={{ selected: current === choice }}
              onPress={() => onChange(choice)}
              style={[
                styles.choice,
                current === choice && styles.choiceSelected,
              ]}
            >
              <Text
                style={[
                  styles.choiceText,
                  current === choice && styles.choiceTextSelected,
                ]}
              >
                {choice}
              </Text>
            </Pressable>
          ))}
          {!field.required && current ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={`Clear ${field.label}`}
              onPress={onClear}
              style={styles.choice}
            >
              <Text style={styles.choiceText}>Clear</Text>
            </Pressable>
          ) : null}
        </View>
      </View>
    );
  }
  const label = `${field.label}${field.required ? " · required" : ""}${field.kind === "quantity" ? ` (${field.unit})` : ""}`;
  return (
    <View style={styles.inputGroup}>
      <Text style={styles.inputLabel}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        value={typeof value === "string" ? value : ""}
        onChangeText={onChange}
        keyboardType={
          field.kind === "number" || field.kind === "quantity"
            ? "decimal-pad"
            : "default"
        }
        placeholder={field.kind === "date" ? "YYYY-MM-DD" : undefined}
        autoCapitalize="sentences"
        style={styles.input}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: "#f7f9f7" },
  content: { gap: 16, padding: 20, paddingBottom: 36 },
  title: { color: "#17201c", fontSize: 28, fontWeight: "700" },
  subtitle: { color: "#46534d", fontSize: 15, lineHeight: 22 },
  inputGroup: { gap: 6 },
  inputLabel: { color: "#203a2e", fontSize: 15, fontWeight: "700" },
  input: {
    backgroundColor: "#fff",
    borderColor: "#68786f",
    borderRadius: 10,
    borderWidth: 1,
    color: "#17201c",
    fontSize: 16,
    minHeight: 50,
    paddingHorizontal: 14,
  },
  choices: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  choice: {
    backgroundColor: "#fff",
    borderColor: "#68786f",
    borderRadius: 18,
    borderWidth: 1,
    paddingHorizontal: 13,
    paddingVertical: 9,
  },
  choiceSelected: { backgroundColor: "#245d3a", borderColor: "#245d3a" },
  choiceText: { color: "#24342b", fontSize: 14 },
  choiceTextSelected: { color: "#fff", fontWeight: "700" },
  empty: { backgroundColor: "#fff", borderRadius: 14, gap: 12, padding: 18 },
  cardTitle: { color: "#17201c", fontSize: 18, fontWeight: "700" },
  note: { backgroundColor: "#eaf0ec", borderRadius: 12, padding: 14 },
  noteText: { color: "#46534d", fontSize: 14, lineHeight: 21 },
  meta: { color: "#596860", fontSize: 13 },
});
