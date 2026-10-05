import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";

import {
  ActionButton,
  LoadingMessage,
  StatusMessage,
} from "../../profile/components/Ui";
import { dailyApi, dailyErrorMessage } from "../api";
import { planningApi } from "../../planning/api";
import type { components } from "@personal-health/api-client";
import {
  customTrackerValue,
  itemTimeLabel,
  itemTitle,
  itemValue,
  type DailyItem,
  type DailyObservation,
} from "../model";

function maybeType(
  value: string | string[] | undefined,
): "event" | "observation" {
  return value === "observation" ? "observation" : "event";
}

export default function DailyItemScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ itemId: string; type?: string }>();
  const type = maybeType(params.type);
  const [item, setItem] = useState<DailyItem | null>(null);
  const [linked, setLinked] = useState<DailyObservation[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const customValue = item ? customTrackerValue(item) : null;
  const customTrackerId = customValue?.tracker_id;
  const customSchemaVersion = customValue?.schema_version;
  const [loadedCustomSchema, setLoadedCustomSchema] = useState<{
    trackerId: string;
    version: number;
    definition: components["schemas"]["TrackerDefinitionV1"];
  } | null>(null);
  const customDefinition =
    loadedCustomSchema &&
    loadedCustomSchema.trackerId === customTrackerId &&
    loadedCustomSchema.version === customSchemaVersion
      ? loadedCustomSchema.definition
      : null;

  useEffect(() => {
    if (!customTrackerId || !customSchemaVersion) return;
    let active = true;
    planningApi
      .listTrackerVersions(
        { tracker_id: customTrackerId },
        { after_version: customSchemaVersion - 1, limit: 1 },
      )
      .then((page) => {
        if (!active) return;
        const version = page.items.find(
          (candidate) => candidate.version === customSchemaVersion,
        );
        if (version) {
          setLoadedCustomSchema({
            trackerId: customTrackerId,
            version: customSchemaVersion,
            definition: version.definition,
          });
        }
      })
      .catch(() => {
        if (active) setLoadedCustomSchema(null);
      });
    return () => {
      active = false;
    };
  }, [customSchemaVersion, customTrackerId]);

  useFocusEffect(
    useCallback(() => {
      let active = true;
      setLoading(true);
      setError(null);
      void (async () => {
        try {
          const result =
            type === "event"
              ? await dailyApi.getEvent({ event_id: params.itemId })
              : await dailyApi.getObservation({
                  observation_id: params.itemId,
                });
          if (!active) return;
          setItem(result);
          if (
            result.object_type === "event" &&
            result.linked_observation_ids.length > 0
          ) {
            const observations = await Promise.all(
              result.linked_observation_ids.map((observation_id) =>
                dailyApi.getObservation({ observation_id }),
              ),
            );
            if (active) setLinked(observations);
          } else if (active) {
            setLinked([]);
          }
        } catch (requestError) {
          if (active) setError(dailyErrorMessage(requestError));
        } finally {
          if (active) setLoading(false);
        }
      })();
      return () => {
        active = false;
      };
      // eslint-disable-next-line react-hooks/exhaustive-deps -- refresh intentionally retriggers the focus load.
    }, [params.itemId, refresh, type]),
  );

  async function archive() {
    if (!item || item.status !== "active") return;
    setBusy(true);
    setError(null);
    try {
      const archived =
        item.object_type === "event"
          ? await dailyApi.archiveEvent(
              { event_id: item.id },
              { expected_revision: item.revision },
            )
          : await dailyApi.archiveObservation(
              { observation_id: item.id },
              { expected_revision: item.revision },
            );
      setItem(archived);
      router.replace("/today");
    } catch (requestError) {
      setError(dailyErrorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  function confirmArchive() {
    Alert.alert(
      "Archive this entry?",
      "It will leave the active timeline, and its history will remain available.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Archive entry",
          style: "destructive",
          onPress: () => void archive(),
        },
      ],
    );
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.nav}>
          <ActionButton
            label="Back to Today"
            secondary
            onPress={() => router.replace("/today")}
          />
        </View>
        {loading ? <LoadingMessage label="Loading entry" /> : null}
        {error && !loading ? (
          <View>
            <StatusMessage
              title="Entry could not load"
              message={error}
              tone="error"
            />
            <ActionButton
              label="Retry entry request"
              onPress={() => setRefresh((value) => value + 1)}
            />
          </View>
        ) : null}
        {!loading && item ? (
          <View style={styles.card}>
            <Text accessibilityRole="header" style={styles.title}>
              {itemTitle(item)}
            </Text>
            <Text style={styles.kind}>
              {item.domain} · {item.object_type}
            </Text>
            <Text style={styles.value}>
              {itemValue(
                item,
                Object.fromEntries(
                  (customDefinition?.fields ?? []).map((field) => [
                    field.id,
                    field.label,
                  ]),
                ),
              )}
            </Text>
            <Text style={styles.meta}>
              {itemTimeLabel(
                item,
                item.object_type === "event"
                  ? item.event.time.timezone
                  : item.observation.time.timezone,
              )}
            </Text>
            <Text style={styles.meta}>
              Recorded from {item.source.name} ·{" "}
              {item.confirmation_status.replaceAll("_", " ")}
            </Text>
            <Text style={styles.meta}>
              Revision {item.revision} · {item.status}
            </Text>
            {customTrackerValue(item) ? (
              <Text style={styles.meta}>
                Tracker {customTrackerValue(item)!.tracker_id} · schema version{" "}
                {customTrackerValue(item)!.schema_version}
              </Text>
            ) : null}
            {customDefinition ? (
              <Text style={styles.meta}>
                {customDefinition.name} · historical schema loaded
              </Text>
            ) : null}
            {item.notes ? <Text style={styles.notes}>{item.notes}</Text> : null}
            {item.object_type === "event" &&
            item.event.payload.kind === "meal" &&
            item.event.payload.foods?.length ? (
              <Text style={styles.body}>
                Foods: {item.event.payload.foods.join(", ")}
              </Text>
            ) : null}
            {item.object_type === "event" &&
            item.event.payload.kind === "sleep" &&
            item.event.payload.quality ? (
              <Text style={styles.body}>
                Sleep quality: {item.event.payload.quality} of 5
              </Text>
            ) : null}
            {linked.map((observation) => (
              <Pressable
                key={observation.id}
                accessibilityRole="button"
                accessibilityLabel={`Edit linked symptom severity, ${itemValue(observation)}`}
                onPress={() =>
                  router.push({
                    pathname: "/daily/item/[itemId]",
                    params: { itemId: observation.id, type: "observation" },
                  })
                }
                style={styles.related}
              >
                <Text style={styles.body}>
                  Linked severity: {itemValue(observation)}
                </Text>
                <Text style={styles.meta}>Open severity Observation</Text>
              </Pressable>
            ))}
            {item.status === "active" ? (
              <View style={styles.actions}>
                {!customTrackerValue(item) ? (
                  <ActionButton
                    label="Edit entry"
                    onPress={() =>
                      router.push({
                        pathname: "/daily/item/[itemId]/edit",
                        params: { itemId: item.id, type: item.object_type },
                      })
                    }
                  />
                ) : null}
                <ActionButton
                  label="Archive entry"
                  secondary
                  busy={busy}
                  onPress={confirmArchive}
                />
              </View>
            ) : (
              <Text style={styles.archived}>
                Archived entries are read-only.
              </Text>
            )}
            {error ? (
              <StatusMessage
                title="Could not save change"
                message={error}
                tone="error"
              />
            ) : null}
            <ActionButton
              label="View entry history"
              secondary
              onPress={() =>
                router.push({
                  pathname: "/daily/item/[itemId]/history",
                  params: { itemId: item.id, type: item.object_type },
                })
              }
            />
          </View>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { backgroundColor: "#f7f9f7", flex: 1 },
  content: { gap: 16, padding: 20, paddingBottom: 36 },
  nav: { alignItems: "flex-start" },
  card: {
    backgroundColor: "#fff",
    borderColor: "#c8d2cb",
    borderRadius: 16,
    borderWidth: 1,
    gap: 12,
    padding: 18,
  },
  title: { color: "#17201c", fontSize: 26, fontWeight: "700" },
  kind: {
    color: "#245d3a",
    fontSize: 14,
    fontWeight: "700",
    textTransform: "capitalize",
  },
  value: { color: "#24342b", fontSize: 19, fontWeight: "600" },
  meta: { color: "#596860", fontSize: 14, lineHeight: 20 },
  body: { color: "#34463b", fontSize: 16, lineHeight: 23 },
  notes: { color: "#34463b", fontSize: 16, lineHeight: 23, paddingTop: 8 },
  related: {
    backgroundColor: "#f3f7f4",
    borderRadius: 12,
    gap: 4,
    padding: 12,
  },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  archived: { color: "#596860", fontSize: 15 },
});
