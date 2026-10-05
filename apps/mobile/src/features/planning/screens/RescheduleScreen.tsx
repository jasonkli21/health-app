import { useLocalSearchParams, useRouter } from "expo-router";
import { useMemo, useState } from "react";
import {
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
} from "react-native";

import { ActionButton, StatusMessage } from "../../profile/components/Ui";
import { planningApi, planningErrorMessage } from "../api";

export default function RescheduleScreen() {
  const params = useLocalSearchParams<{
    key?: string;
    scheduleRevision?: string;
    overrideRevision?: string;
    timezone?: string;
    dueAt?: string;
  }>();
  const router = useRouter();
  const [dueAt, setDueAt] = useState(params.dueAt ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const validRoute = useMemo(
    () => Boolean(params.key && Number(params.scheduleRevision) >= 1),
    [params.key, params.scheduleRevision],
  );

  async function save() {
    setError(null);
    if (!validRoute || !params.key) {
      setError(
        "This occurrence is missing its schedule details. Return to Today and refresh.",
      );
      return;
    }
    const offsetDateTime =
      /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})$/i;
    if (
      !offsetDateTime.test(dueAt.trim()) ||
      Number.isNaN(Date.parse(dueAt.trim()))
    ) {
      setError(
        "Enter a valid ISO date and time with a UTC offset, such as 2026-10-05T17:00:00-07:00.",
      );
      return;
    }
    const parsedOverride = params.overrideRevision
      ? Number(params.overrideRevision)
      : null;
    if (
      parsedOverride !== null &&
      (!Number.isInteger(parsedOverride) || parsedOverride < 1)
    ) {
      setError(
        "This occurrence revision is invalid. Return to Today and refresh.",
      );
      return;
    }
    setBusy(true);
    try {
      await planningApi.updatePlanOccurrence(
        { occurrence_key: params.key },
        {
          expected_schedule_revision: Number(params.scheduleRevision),
          expected_override_revision: parsedOverride,
          state: "rescheduled",
          rescheduled_at: new Date(dueAt.trim()).toISOString(),
        },
      );
      router.back();
    } catch (requestError) {
      setError(
        `${planningErrorMessage(requestError)} Refresh Today before trying again.`,
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text accessibilityRole="header" style={styles.title}>
          Reschedule planned item
        </Text>
        <Text style={styles.subtitle}>
          Enter the new due time with its UTC offset. The original occurrence
          stays linked to this change.
          {params.timezone ? ` Schedule timezone: ${params.timezone}.` : ""}
        </Text>
        {error ? (
          <StatusMessage
            title="Could not reschedule"
            message={error}
            tone="error"
          />
        ) : null}
        <Text style={styles.label}>New date and time with offset</Text>
        <TextInput
          accessibilityLabel="New date and time with offset"
          value={dueAt}
          onChangeText={setDueAt}
          placeholder="2026-10-05T17:00:00-07:00"
          autoCapitalize="none"
          keyboardType="default"
          style={styles.input}
        />
        <ActionButton
          label="Save new time"
          busy={busy}
          onPress={() => void save()}
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

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: "#f7f9f7" },
  content: { gap: 16, padding: 20, paddingBottom: 36 },
  title: { color: "#17201c", fontSize: 28, fontWeight: "700" },
  subtitle: { color: "#46534d", fontSize: 15, lineHeight: 22 },
  label: { color: "#203a2e", fontSize: 15, fontWeight: "700" },
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
});
