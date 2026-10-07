import { useCallback, useRef, useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import type { components } from "@personal-health/api-client";

import { sessionStore } from "../../../auth/sessionStore";
import {
  ActionButton,
  LoadingMessage,
  StatusMessage,
} from "../../profile/components/Ui";
import { insightsApi, insightsErrorMessage } from "../api";

type AnalyticsHistoryEntry = components["schemas"]["AnalyticsHistoryEntry"];
type JsonObject = Record<string, unknown>;

function object(value: unknown): JsonObject {
  return typeof value === "object" && value !== null
    ? (value as JsonObject)
    : {};
}

export default function AnalyticsEvidenceScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{
    objectId: string;
    revision: string;
  }>();
  const [entry, setEntry] = useState<AnalyticsHistoryEntry | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const cancelCurrent = useRef<(() => void) | null>(null);

  const loadEvidence = useCallback(() => {
    cancelCurrent.current?.();
    let active = true;
    const epoch = sessionStore.getSnapshot().epoch;
    cancelCurrent.current = () => {
      active = false;
    };
    setLoading(true);
    setError(null);
    setEntry(null);
    void insightsApi
      .getAnalyticsHistory({
        artifact_id: params.objectId,
        revision: Number(params.revision),
      })
      .then((result) => {
        if (active && sessionStore.getSnapshot().epoch === epoch)
          setEntry(result);
      })
      .catch((requestError: unknown) => {
        if (active && sessionStore.getSnapshot().epoch === epoch)
          setError(insightsErrorMessage(requestError));
      })
      .finally(() => {
        if (active && sessionStore.getSnapshot().epoch === epoch)
          setLoading(false);
      });
  }, [params.objectId, params.revision]);

  useFocusEffect(
    useCallback(() => {
      loadEvidence();
      return () => cancelCurrent.current?.();
    }, [loadEvidence]),
  );

  const snapshot = object(entry?.snapshot);
  const payload = object(snapshot.payload);
  const result = object(payload.result);

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        <ActionButton
          label="Back to Insights"
          secondary
          onPress={() => router.back()}
        />
        <Text accessibilityRole="header" style={styles.title}>
          Analysis evidence
        </Text>
        <Text style={styles.meta}>
          Exact saved revision {entry?.revision ?? params.revision} ·{" "}
          {String(snapshot.object_type ?? "analytics")}
        </Text>
        {loading ? <LoadingMessage label="Loading evidence snapshot" /> : null}
        {error ? (
          <View>
            <StatusMessage
              title="Evidence could not load"
              message={error}
              tone="error"
            />
            <ActionButton
              label="Retry evidence request"
              onPress={loadEvidence}
            />
          </View>
        ) : null}
        {!loading && entry ? (
          <View style={styles.card}>
            <Text style={styles.heading}>
              {String(snapshot.title ?? payload.title ?? "Derived signal")}
            </Text>
            <Text style={styles.meta}>
              {String(payload.signal_kind ?? payload.kind ?? "analysis")} ·{" "}
              {String(
                result.method_version ??
                  payload.method_version ??
                  "method unavailable",
              )}
            </Text>
            {result.from_date || result.to_date ? (
              <Text style={styles.meta}>
                Original window: {String(result.from_date ?? "?")}–
                {String(result.to_date ?? "?")} ·{" "}
                {String(result.timezone ?? "")}
              </Text>
            ) : null}
            {result.coverage ? (
              <Text style={styles.meta}>
                Coverage: {String(object(result.coverage).known_days ?? "?")}/
                {String(object(result.coverage).calendar_days ?? "?")} known
                days
              </Text>
            ) : null}
            <Text style={styles.body}>
              This view shows the stored result cited by the insight. It does
              not resolve to a newer recomputation.
            </Text>
            <Text selectable style={styles.result}>
              {JSON.stringify(result, null, 2) ?? "No stored result"}
            </Text>
            {Array.isArray(result.evidence_refs) ? (
              <Text style={styles.meta}>
                {result.evidence_refs.length} source revisions in this saved
                analysis
              </Text>
            ) : null}
          </View>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: "#f5f7f4" },
  content: { gap: 14, padding: 18 },
  title: { color: "#17201c", fontSize: 28, fontWeight: "700" },
  card: {
    backgroundColor: "#fff",
    borderColor: "#c8d2cb",
    borderRadius: 14,
    borderWidth: 1,
    gap: 10,
    padding: 16,
  },
  heading: { color: "#17201c", fontSize: 18, fontWeight: "700" },
  body: { color: "#34463b", fontSize: 14, lineHeight: 20 },
  meta: { color: "#596860", fontSize: 13, lineHeight: 18 },
  result: {
    color: "#17201c",
    fontFamily: "monospace",
    fontSize: 12,
    lineHeight: 17,
  },
});
