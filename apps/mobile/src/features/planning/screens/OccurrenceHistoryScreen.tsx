import { useEffect, useState } from "react";
import { useLocalSearchParams, useRouter } from "expo-router";
import { SafeAreaView, ScrollView, StyleSheet, Text, View } from "react-native";
import type { components } from "@personal-health/api-client";

import {
  ActionButton,
  LoadingMessage,
  StatusMessage,
} from "../../profile/components/Ui";
import { planningApi, planningErrorMessage } from "../api";

type Entry = components["schemas"]["OccurrenceHistoryEntry"];
const PAGE_SIZE = 50;

export default function OccurrenceHistoryScreen() {
  const params = useLocalSearchParams<{ key?: string }>();
  const router = useRouter();
  const [items, setItems] = useState<Entry[]>([]);
  const [nextAfter, setNextAfter] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!params.key) return;
    let active = true;
    planningApi
      .listPlanOccurrenceHistory(
        { occurrence_key: params.key },
        { limit: PAGE_SIZE },
      )
      .then((page) => {
        if (!active) return;
        setItems(page.items);
        setNextAfter(page.next_after_revision);
      })
      .catch((requestError: unknown) => {
        if (active) setError(planningErrorMessage(requestError));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [params.key]);

  async function loadMore() {
    if (!params.key || nextAfter === null) return;
    setBusy(true);
    setError(null);
    try {
      const page = await planningApi.listPlanOccurrenceHistory(
        { occurrence_key: params.key },
        { after_revision: nextAfter, limit: PAGE_SIZE },
      );
      setItems((current) => [...current, ...page.items]);
      setNextAfter(page.next_after_revision);
    } catch (requestError) {
      setError(planningErrorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  if (!params.key) {
    return (
      <SafeAreaView style={styles.safeArea}>
        <StatusMessage
          title="Occurrence key is missing"
          message="Return to Today and open action history again."
          tone="error"
        />
        <ActionButton label="Back" onPress={() => router.back()} />
      </SafeAreaView>
    );
  }
  if (loading) return <LoadingMessage label="Loading occurrence history" />;
  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text accessibilityRole="header" style={styles.title}>
          Occurrence action history
        </Text>
        <Text selectable style={styles.key}>
          {params.key}
        </Text>
        {error ? (
          <StatusMessage
            title="History could not load"
            message={error}
            tone="error"
          />
        ) : null}
        {items.length === 0 && !error ? (
          <Text style={styles.meta}>No recorded changes are available.</Text>
        ) : null}
        {items.map((entry) => (
          <View key={entry.revision} style={styles.card}>
            <Text style={styles.cardTitle}>
              Change {entry.revision} · {entry.action}
            </Text>
            <Text style={styles.meta}>
              Recorded {entry.acted_at} · schedule revision{" "}
              {entry.schedule_revision}
            </Text>
            {entry.rescheduled_at ? (
              <Text style={styles.meta}>
                Moved due time: {entry.rescheduled_at}
              </Text>
            ) : null}
            {entry.linked_event_id ? (
              <Text style={styles.meta}>
                Linked Event: {entry.linked_event_id}
              </Text>
            ) : null}
            {entry.linked_observation_id ? (
              <Text style={styles.meta}>
                Linked Observation: {entry.linked_observation_id}
              </Text>
            ) : null}
          </View>
        ))}
        {nextAfter !== null ? (
          <ActionButton
            label="Load older changes"
            secondary
            busy={busy}
            onPress={() => void loadMore()}
          />
        ) : null}
        <ActionButton label="Back" onPress={() => router.back()} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: "#f7f9f7" },
  content: { gap: 16, padding: 20, paddingBottom: 36 },
  title: { color: "#17201c", fontSize: 28, fontWeight: "700" },
  key: { color: "#596860", fontSize: 12, lineHeight: 18 },
  card: {
    backgroundColor: "#fff",
    borderColor: "#c8d2cb",
    borderRadius: 14,
    borderWidth: 1,
    gap: 8,
    padding: 14,
  },
  cardTitle: { color: "#17201c", fontSize: 18, fontWeight: "700" },
  meta: { color: "#596860", fontSize: 13 },
});
