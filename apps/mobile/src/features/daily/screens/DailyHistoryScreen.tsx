import { useCallback, useRef, useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";

import {
  ActionButton,
  LoadingMessage,
  StatusMessage,
} from "../../profile/components/Ui";
import { dailyApi, dailyErrorMessage } from "../api";
import { itemTitle, itemValue, type DailyItem } from "../model";
import { RequestScope, requestNextPage } from "../../profile/requestScope";
import type { components } from "@personal-health/api-client";

type HistoryEntry = components["schemas"]["DailyHistoryEntry"];
type HistoryResponse = components["schemas"]["DailyHistoryResponse"];

function selectedType(
  value: string | string[] | undefined,
): "event" | "observation" {
  return value === "observation" ? "observation" : "event";
}

function snapshot(entry: HistoryEntry): DailyItem {
  return entry.snapshot as DailyItem;
}

export default function DailyHistoryScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{
    itemId: string;
    type?: string;
    revision?: string;
  }>();
  const type = selectedType(params.type);
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [nextRevision, setNextRevision] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const requestScope = useRef(new RequestScope());
  const targetRevision = params.revision ? Number(params.revision) : undefined;
  const scopeKey = `history:${type}:${params.itemId}:${targetRevision ?? "all"}:${refresh}`;

  useFocusEffect(
    useCallback(() => {
      const scope = requestScope.current.start(scopeKey);
      setLoading(true);
      setError(null);
      setEntries([]);
      setNextRevision(null);
      setLoadingMore(false);
      void (async () => {
        try {
          const result =
            type === "event"
              ? await dailyApi.listEventHistory(
                  { event_id: params.itemId },
                  targetRevision
                    ? { revision: targetRevision, limit: 1 }
                    : { limit: 50 },
                )
              : await dailyApi.listObservationHistory(
                  { observation_id: params.itemId },
                  targetRevision
                    ? { revision: targetRevision, limit: 1 }
                    : { limit: 50 },
                );
          if (!requestScope.current.isCurrent(scope)) return;
          setEntries(result.items);
          setNextRevision(result.next_after_revision);
        } catch (requestError) {
          if (requestScope.current.isCurrent(scope))
            setError(dailyErrorMessage(requestError));
        } finally {
          if (requestScope.current.isCurrent(scope)) setLoading(false);
        }
      })();
      return () => requestScope.current.invalidate(scope);
    }, [params.itemId, scopeKey, targetRevision, type]),
  );

  async function loadMore() {
    if (nextRevision === null) return;
    const scope = requestScope.current.tokenFor(scopeKey);
    if (!scope) return;
    const afterRevision = nextRevision;
    await requestNextPage(
      requestScope.current,
      scope,
      String(afterRevision),
      () =>
        type === "event"
          ? dailyApi.listEventHistory(
              { event_id: params.itemId },
              { after_revision: afterRevision, limit: 50 },
            )
          : dailyApi.listObservationHistory(
              { observation_id: params.itemId },
              { after_revision: afterRevision, limit: 50 },
            ),
      {
        onStart: () => {
          setLoadingMore(true);
          setError(null);
        },
        onSuccess: (page: HistoryResponse) => {
          setEntries((current) => [...current, ...page.items]);
          setNextRevision(page.next_after_revision);
        },
        onError: (requestError) => setError(dailyErrorMessage(requestError)),
        onFinish: () => setLoadingMore(false),
      },
    );
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        <ActionButton
          label="Back to entry"
          secondary
          onPress={() => router.back()}
        />
        <Text accessibilityRole="header" style={styles.title}>
          {targetRevision
            ? `Evidence snapshot · revision ${targetRevision}`
            : "Entry history"}
        </Text>
        {targetRevision ? (
          <Text style={styles.hint}>
            This is the exact saved revision cited by the analysis. Current
            edits are shown separately on the entry screen.
          </Text>
        ) : null}
        {error && !loading ? (
          <View>
            <StatusMessage
              title="History could not load"
              message={error}
              tone="error"
            />
            <ActionButton
              label="Retry history request"
              onPress={() => setRefresh((value) => value + 1)}
            />
          </View>
        ) : null}
        {loading ? <LoadingMessage label="Loading entry history" /> : null}
        {!loading && entries.length === 0 ? (
          <Text style={styles.hint}>No history is available.</Text>
        ) : null}
        {entries.map((entry) => {
          const item = snapshot(entry);
          return (
            <View key={entry.revision} style={styles.card}>
              <Text style={styles.revision}>
                Revision {entry.revision} · {entry.reason}
                {entry.revision === targetRevision ? " · cited evidence" : ""}
              </Text>
              <Text style={styles.itemTitle}>{itemTitle(item)}</Text>
              <Text style={styles.body}>{itemValue(item)}</Text>
              <Text style={styles.meta}>
                Recorded {new Date(entry.recorded_at).toLocaleString()}
              </Text>
              {item.notes ? (
                <Text style={styles.body}>{item.notes}</Text>
              ) : null}
              <Text style={styles.meta}>
                Status: {item.status} · source: {item.source.name}
              </Text>
            </View>
          );
        })}
        {nextRevision !== null ? (
          <ActionButton
            label="Load older history"
            onPress={() => void loadMore()}
            busy={loadingMore}
            disabled={loadingMore}
            secondary
          />
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { backgroundColor: "#f7f9f7", flex: 1 },
  content: { gap: 14, padding: 20, paddingBottom: 36 },
  title: { color: "#17201c", fontSize: 28, fontWeight: "700" },
  card: {
    backgroundColor: "#fff",
    borderColor: "#c8d2cb",
    borderRadius: 14,
    borderWidth: 1,
    gap: 6,
    padding: 15,
  },
  revision: {
    color: "#245d3a",
    fontSize: 14,
    fontWeight: "700",
    textTransform: "capitalize",
  },
  itemTitle: { color: "#17201c", fontSize: 17, fontWeight: "700" },
  body: { color: "#34463b", fontSize: 15, lineHeight: 22 },
  meta: { color: "#596860", fontSize: 13 },
  hint: { color: "#46534d", fontSize: 16, lineHeight: 23 },
});
