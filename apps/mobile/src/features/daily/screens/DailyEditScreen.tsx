import { useCallback, useState } from "react";
import { ScrollView, StyleSheet, View } from "react-native";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";

import {
  LoadingMessage,
  StatusMessage,
  ActionButton,
} from "../../profile/components/Ui";
import { dailyApi, dailyErrorMessage } from "../api";
import { DailyEntryForm } from "../components/DailyEntryForm";
import type {
  DailyDomain,
  DailyItem,
  EventRecord,
  ObservationRecord,
} from "../model";

function selectedType(
  value: string | string[] | undefined,
): "event" | "observation" {
  return value === "observation" ? "observation" : "event";
}

export default function DailyEditScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ itemId: string; type?: string }>();
  const type = selectedType(params.type);
  const [item, setItem] = useState<DailyItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);

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
          if (active) setItem(result);
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

  async function update(record: EventRecord | ObservationRecord) {
    if (!item) return;
    if (item.status !== "active")
      throw new Error("Archived entries cannot be edited.");
    if (item.object_type === "event") {
      await dailyApi.updateEvent(
        { event_id: item.id },
        { expected_revision: item.revision, event: record as EventRecord },
      );
    } else {
      await dailyApi.updateObservation(
        { observation_id: item.id },
        {
          expected_revision: item.revision,
          observation: record as ObservationRecord,
        },
      );
    }
    router.replace({
      pathname: "/daily/item/[itemId]",
      params: { itemId: item.id, type: item.object_type },
    });
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
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
          <DailyEntryForm
            key={`${item.id}:${item.revision}:${refresh}`}
            domain={item.domain as DailyDomain}
            initialItem={item}
            submitLabel="Save changes"
            onCancel={() => router.back()}
            onUpdate={update}
            onConflictReload={() => setRefresh((value) => value + 1)}
          />
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { backgroundColor: "#f7f9f7", flex: 1 },
  content: { flex: 1 },
});
