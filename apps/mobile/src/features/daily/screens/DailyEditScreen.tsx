import { useCallback, useRef, useState } from "react";
import { ScrollView, StyleSheet, View } from "react-native";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";

import {
  LoadingMessage,
  StatusMessage,
  ActionButton,
} from "../../profile/components/Ui";
import { dailyApi, dailyErrorMessage } from "../api";
import { customTrackerValue } from "../model";
import { DailyEntryForm } from "../components/DailyEntryForm";
import type { EventRecord, ObservationRecord } from "../model";
import {
  acceptDailyRefresh,
  EMPTY_DAILY_EDIT_STATE,
  recordDailyDraft,
} from "../editState";

function selectedType(
  value: string | string[] | undefined,
): "event" | "observation" {
  return value === "observation" ? "observation" : "event";
}

export default function DailyEditScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ itemId: string; type?: string }>();
  const type = selectedType(params.type);
  const [editState, setEditState] = useState(EMPTY_DAILY_EDIT_STATE);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const explicitlyReloading = useRef(false);
  const item = editState.item?.id === params.itemId ? editState.item : null;
  const draft = item ? editState.draft : null;

  useFocusEffect(
    useCallback(() => {
      let active = true;
      const replaceDraft = explicitlyReloading.current;
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
          if (active) {
            explicitlyReloading.current = false;
            setEditState((state) =>
              acceptDailyRefresh(state, result, replaceDraft),
            );
          }
        } catch (requestError) {
          if (active) {
            explicitlyReloading.current = false;
            setError(dailyErrorMessage(requestError));
          }
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

  async function update(
    record: EventRecord | ObservationRecord,
    aiUseAllowed: boolean,
  ) {
    if (!item) return;
    if (item.status !== "active")
      throw new Error("Archived entries cannot be edited.");
    if (item.object_type === "event") {
      const updated = await dailyApi.updateEvent(
        { event_id: item.id },
        {
          expected_revision: item.revision,
          event: record as EventRecord,
          ai_use_allowed: aiUseAllowed,
        },
      );
      setEditState((state) => acceptDailyRefresh(state, updated, true));
    } else {
      const updated = await dailyApi.updateObservation(
        { observation_id: item.id },
        {
          expected_revision: item.revision,
          observation: record as ObservationRecord,
          ai_use_allowed: aiUseAllowed,
        },
      );
      setEditState((state) => acceptDailyRefresh(state, updated, true));
    }
    router.replace({
      pathname: "/daily/item/[itemId]",
      params: { itemId: item.id, type: item.object_type },
    });
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        {loading && !item ? <LoadingMessage label="Loading entry" /> : null}
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
        {item && customTrackerValue(item) ? (
          <StatusMessage
            title="Custom tracker entry is read-only"
            message="This entry keeps the tracker schema version it was created with. Edit the tracker definition from Plan to make a new version for future entries."
          />
        ) : null}
        {item && draft && !customTrackerValue(item) ? (
          <DailyEntryForm
            key={`${item.id}:${editState.formGeneration}`}
            domain={item.domain}
            initialItem={item}
            initialDraft={draft}
            submitLabel="Save changes"
            onCancel={() => router.back()}
            onUpdate={update}
            onDraftChange={(nextDraft) =>
              setEditState((state) => recordDailyDraft(state, nextDraft))
            }
            onConflictReload={() => {
              explicitlyReloading.current = true;
              setRefresh((value) => value + 1);
            }}
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
