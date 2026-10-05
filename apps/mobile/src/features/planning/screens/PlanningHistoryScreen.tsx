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

type Kind = "goal" | "regimen" | "plan" | "context" | "tracker_definition";
type Entry = components["schemas"]["PlanningHistoryEntry"];
const PAGE_SIZE = 50;

async function historyPage(kind: Kind, id: string, afterRevision: number) {
  const query = { after_revision: afterRevision, limit: PAGE_SIZE };
  if (kind === "goal")
    return planningApi.listGoalHistory({ goal_id: id }, query);
  if (kind === "regimen")
    return planningApi.listRegimenHistory({ regimen_id: id }, query);
  if (kind === "plan")
    return planningApi.listPlanHistory({ plan_id: id }, query);
  if (kind === "context")
    return planningApi.listContextHistory({ context_id: id }, query);
  return planningApi.listTrackerHistory({ tracker_id: id }, query);
}

export default function PlanningHistoryScreen() {
  const params = useLocalSearchParams<{ kind?: string; id?: string }>();
  const router = useRouter();
  const kind = params.kind as Kind;
  const validRoute = Boolean(
    params.id &&
      ["goal", "regimen", "plan", "context", "tracker_definition"].includes(
        kind,
      ),
  );
  const [items, setItems] = useState<Entry[]>([]);
  const [nextAfter, setNextAfter] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!validRoute || !params.id) return;
    let active = true;
    historyPage(kind, params.id, 0)
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
  }, [kind, params.id, validRoute]);

  async function loadMore() {
    if (!params.id || nextAfter === null) return;
    setBusy(true);
    setError(null);
    try {
      const page = await historyPage(kind, params.id, nextAfter);
      setItems((current) => [...current, ...page.items]);
      setNextAfter(page.next_after_revision);
    } catch (requestError) {
      setError(planningErrorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  if (!validRoute) {
    return (
      <SafeAreaView style={styles.safeArea}>
        <StatusMessage
          title="History link is incomplete"
          message="Return to Plan and reopen the item."
          tone="error"
        />
        <ActionButton label="Back" onPress={() => router.back()} />
      </SafeAreaView>
    );
  }
  if (loading) return <LoadingMessage label="Loading planning history" />;
  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text accessibilityRole="header" style={styles.title}>
          Planning history
        </Text>
        <Text style={styles.subtitle}>
          {kind?.replaceAll("_", " ") ?? "Planning item"} · {params.id}
        </Text>
        {error ? (
          <StatusMessage
            title="History could not load"
            message={error}
            tone="error"
          />
        ) : null}
        {items.length === 0 && !error ? (
          <Text style={styles.meta}>No revisions are available.</Text>
        ) : null}
        {items.map((entry) => (
          <View key={entry.revision} style={styles.card}>
            <Text style={styles.cardTitle}>
              Revision {entry.revision} · {entry.reason}
            </Text>
            <Text style={styles.meta}>{entry.recorded_at}</Text>
            <Text style={styles.body}>
              Lifecycle: {String(entry.snapshot.lifecycle ?? "unknown")}
            </Text>
            <Text style={styles.body}>Payload</Text>
            <Text selectable style={styles.payload}>
              {JSON.stringify(
                entry.snapshot.payload ?? entry.snapshot,
                null,
                2,
              )}
            </Text>
          </View>
        ))}
        {nextAfter !== null ? (
          <ActionButton
            label="Load older revisions"
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
  subtitle: { color: "#46534d", fontSize: 14, lineHeight: 20 },
  card: {
    backgroundColor: "#fff",
    borderColor: "#c8d2cb",
    borderRadius: 14,
    borderWidth: 1,
    gap: 8,
    padding: 14,
  },
  cardTitle: { color: "#17201c", fontSize: 18, fontWeight: "700" },
  body: { color: "#46534d", fontSize: 14, fontWeight: "600" },
  meta: { color: "#596860", fontSize: 13 },
  payload: {
    color: "#24342b",
    fontFamily: "monospace",
    fontSize: 12,
    lineHeight: 18,
  },
});
