import { useCallback, useRef, useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";

import { profileApi, profileErrorMessage } from "../api";
import { ProfileValueDisplay } from "../components/ProfileValueDisplay";
import { ActionButton, LoadingMessage, StatusMessage } from "../components/Ui";
import { formatInstant } from "../model";
import type { components } from "@personal-health/api-client";
import { RequestScope, requestNextPage } from "../requestScope";

type HistoryEntry = components["schemas"]["ProfileHistoryEntry"];
const PAGE_SIZE = 50;

export default function ProfileHistoryScreen() {
  const { itemId } = useLocalSearchParams<{ itemId: string }>();
  const router = useRouter();
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [nextRevision, setNextRevision] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const requestScope = useRef(new RequestScope());
  const scopeKey = `history:${itemId}:${reload}`;

  useFocusEffect(
    useCallback(() => {
      const scope = requestScope.current.start(scopeKey);
      setLoading(true);
      setError(null);
      setEntries([]);
      setNextRevision(null);
      setLoadingMore(false);
      void profileApi
        .listProfileHistory(
          { item_id: itemId },
          { after_revision: 0, limit: PAGE_SIZE },
        )
        .then(
          (response) => {
            if (requestScope.current.isCurrent(scope)) {
              setEntries(response.items);
              setNextRevision(response.next_after_revision);
            }
          },
          (requestError: unknown) => {
            if (requestScope.current.isCurrent(scope)) {
              setError(profileErrorMessage(requestError));
            }
          },
        )
        .finally(() => {
          if (requestScope.current.isCurrent(scope)) setLoading(false);
        });
      return () => {
        requestScope.current.invalidate(scope);
      };
      // Retry state intentionally recreates this focus callback to refetch server truth.
      // eslint-disable-next-line react-hooks/exhaustive-deps -- retry token is an effect trigger.
    }, [itemId, reload, scopeKey]),
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
        profileApi.listProfileHistory(
          { item_id: itemId },
          { after_revision: afterRevision, limit: PAGE_SIZE },
        ),
      {
        onStart: () => {
          setLoadingMore(true);
          setError(null);
        },
        onSuccess: (response) => {
          setEntries((current) => [...current, ...response.items]);
          setNextRevision(response.next_after_revision);
        },
        onError: (requestError) => setError(profileErrorMessage(requestError)),
        onFinish: () => setLoadingMore(false),
      },
    );
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      {loading ? <LoadingMessage label="Loading Profile history" /> : null}
      {error ? (
        <View style={styles.content}>
          <StatusMessage
            title="Profile history could not load"
            message={error}
            tone="error"
          />
          <ActionButton
            label="Retry history request"
            onPress={() => setReload((value) => value + 1)}
          />
        </View>
      ) : null}
      {!loading && !error ? (
        <ScrollView contentContainerStyle={styles.content}>
          <Text accessibilityRole="header" style={styles.title}>
            Profile history
          </Text>
          {entries.length === 0 ? (
            <Text style={styles.body}>No revisions are available.</Text>
          ) : null}
          {entries.map((entry) => (
            <View key={entry.revision} style={styles.card}>
              <Text accessibilityRole="header" style={styles.revision}>
                Revision {entry.revision} · {entry.reason}
              </Text>
              <Text style={styles.body}>{entry.snapshot.profile.label}</Text>
              <ProfileValueDisplay value={entry.snapshot.profile.value} />
              <Text style={styles.meta}>
                Effective {formatInstant(entry.snapshot.valid_from)} –{" "}
                {formatInstant(entry.snapshot.valid_to)}
              </Text>
              {entry.snapshot.notes ? (
                <Text style={styles.meta}>Notes: {entry.snapshot.notes}</Text>
              ) : null}
              <Text style={styles.meta}>
                AI use:{" "}
                {entry.snapshot.permissions.ai_use_allowed
                  ? "allowed"
                  : "not allowed"}
                ; use by other apps and health domains through Personal AI:{" "}
                {entry.snapshot.permissions.cross_domain_use_allowed
                  ? "allowed"
                  : "not allowed"}
              </Text>
              <Text style={styles.meta}>
                Source: {entry.snapshot.source.name} (
                {entry.snapshot.source.kind}); confirmation:{" "}
                {entry.snapshot.confirmation_status}
              </Text>
              <Text style={styles.meta}>
                Recorded {formatInstant(entry.recorded_at)} by{" "}
                {entry.actor_kind}
              </Text>
              <Text style={styles.meta}>Status: {entry.snapshot.status}</Text>
            </View>
          ))}
          {nextRevision !== null ? (
            <ActionButton
              label="Load more revisions"
              onPress={() => void loadMore()}
              busy={loadingMore}
              secondary
            />
          ) : null}
          <ActionButton
            label="Back to Profile item"
            onPress={() => router.back()}
            secondary
          />
        </ScrollView>
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { backgroundColor: "#f7f9f7", flex: 1 },
  content: { gap: 16, padding: 20, paddingBottom: 36 },
  title: { color: "#17201c", fontSize: 28, fontWeight: "700" },
  revision: { color: "#17201c", fontSize: 18, fontWeight: "700" },
  body: { color: "#34463b", fontSize: 16, lineHeight: 23 },
  meta: { color: "#596860", fontSize: 14, lineHeight: 20 },
  card: {
    backgroundColor: "#fff",
    borderColor: "#c8d2cb",
    borderRadius: 14,
    borderWidth: 1,
    gap: 10,
    padding: 16,
  },
});
