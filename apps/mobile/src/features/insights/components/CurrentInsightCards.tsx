import { useCallback, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import type { components } from "@personal-health/api-client";

import { sessionStore } from "../../../auth/sessionStore";
import { insightsApi } from "../api";

type Insight = components["schemas"]["InsightResponse"];

export function CurrentInsightCards() {
  const router = useRouter();
  const [items, setItems] = useState<Insight[]>([]);
  const [loading, setLoading] = useState(true);

  useFocusEffect(
    useCallback(() => {
      let active = true;
      const epoch = sessionStore.getSnapshot().epoch;
      setLoading(true);
      void insightsApi
        .listInsights({ state: "current", limit: 3 })
        .then((response) => {
          if (!active || sessionStore.getSnapshot().epoch !== epoch) return;
          const now = Date.now();
          setItems(
            response.items.filter(
              (item) =>
                item.state === "current" &&
                Date.parse(item.insight.expires_at) > now,
            ),
          );
        })
        .catch(() => {
          if (active && sessionStore.getSnapshot().epoch === epoch)
            setItems([]);
        })
        .finally(() => {
          if (active && sessionStore.getSnapshot().epoch === epoch)
            setLoading(false);
        });
      return () => {
        active = false;
      };
    }, []),
  );

  return (
    <View style={styles.section}>
      <Text accessibilityRole="header" style={styles.heading}>
        Current insights
      </Text>
      {loading ? (
        <Text style={styles.meta}>Loading current summaries…</Text>
      ) : items.length ? (
        items.map((item) => (
          <View key={item.id} style={styles.card}>
            <Text style={styles.title}>{item.title}</Text>
            <Text style={styles.body}>{item.insight.explanation}</Text>
            <Text style={styles.meta}>
              {item.insight.evidence_refs.length} evidence revisions · expires{" "}
              {new Date(item.insight.expires_at).toLocaleDateString()}
            </Text>
          </View>
        ))
      ) : (
        <Text style={styles.meta}>No current evidence-linked insights.</Text>
      )}
      <Pressable
        accessibilityRole="button"
        onPress={() => router.push("/insights")}
        style={styles.link}
      >
        <Text style={styles.linkText}>Open Insights and experiments</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  section: {
    backgroundColor: "#edf3ef",
    borderRadius: 16,
    gap: 10,
    padding: 16,
  },
  heading: { color: "#17201c", fontSize: 20, fontWeight: "700" },
  card: {
    backgroundColor: "#fff",
    borderColor: "#c8d2cb",
    borderRadius: 12,
    borderWidth: 1,
    gap: 5,
    padding: 12,
  },
  title: { color: "#17201c", fontSize: 16, fontWeight: "700" },
  body: { color: "#34463b", fontSize: 14, lineHeight: 20 },
  meta: { color: "#596860", fontSize: 13, lineHeight: 18 },
  link: { alignSelf: "flex-start", minHeight: 40, justifyContent: "center" },
  linkText: { color: "#245d3a", fontSize: 15, fontWeight: "700" },
});
