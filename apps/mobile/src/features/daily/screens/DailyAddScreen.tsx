import { useLocalSearchParams, useRouter } from "expo-router";
import { useState } from "react";
import {
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { DailyEntryForm } from "../components/DailyEntryForm";
import { activeDailyCreateRecovery, dailyApi, DailyUserError } from "../api";
import {
  DAILY_DOMAINS,
  type DailyCreateRequest,
  type DailyDomain,
  type DailyDraft,
} from "../model";

function isDomain(value: unknown): value is DailyDomain {
  return (
    typeof value === "string" &&
    DAILY_DOMAINS.some((entry) => entry.value === value)
  );
}

function pendingPrimary(
  request: DailyCreateRequest,
): { id: string; type: "event" | "observation" } | null {
  const event = request.events?.[0];
  if (event) return { id: event.id, type: "event" };
  const observation = request.observations?.[0];
  return observation ? { id: observation.id, type: "observation" } : null;
}

export default function DailyAddScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ domain?: string }>();
  const pending = activeDailyCreateRecovery.retryOriginal();
  const defaultDomain =
    pending?.domain ?? (isDomain(params.domain) ? params.domain : "nutrition");
  const [domain, setDomain] = useState<DailyDomain>(defaultDomain);
  const [hasUncertainSave, setHasUncertainSave] = useState(
    activeDailyCreateRecovery.isUncertain,
  );

  async function submitAttempt(
    attempt: NonNullable<
      ReturnType<typeof activeDailyCreateRecovery.retryOriginal>
    >,
  ) {
    try {
      const result = await dailyApi.createDailyEntry(attempt.request);
      activeDailyCreateRecovery.resolve();
      setHasUncertainSave(false);
      const item = [...result.events, ...result.observations].find(
        (candidate) => candidate.id === attempt.primaryId,
      );
      const target = item
        ? { id: item.id, type: item.object_type }
        : pendingPrimary(attempt.request);
      if (!target)
        throw new DailyUserError(
          "The saved entry could not be identified. Open Today to find it.",
        );
      router.replace({
        pathname: "/daily/item/[itemId]",
        params: {
          itemId: target.id,
          type: target.type,
        },
      });
    } catch (error) {
      const uncertain = activeDailyCreateRecovery.markFailure(attempt, error);
      setHasUncertainSave(uncertain);
      if (uncertain) {
        throw new DailyUserError(
          "The save result is uncertain. Retry the original save to check whether it completed.",
        );
      }
      throw error;
    }
  }

  async function create(request: DailyCreateRequest, draft: DailyDraft) {
    const primary = pendingPrimary(request);
    if (!primary)
      throw new DailyUserError("Add at least one entry before saving.");
    const attempt = activeDailyCreateRecovery.prepare({
      request,
      primaryId: primary.id,
      domain,
      draft: { ...draft },
    });
    await submitAttempt(attempt);
  }

  async function retryOriginalSave() {
    const attempt = activeDailyCreateRecovery.retryOriginal();
    if (attempt) await submitAttempt(attempt);
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.page}>
        <View style={styles.header}>
          <Text accessibilityRole="header" style={styles.title}>
            Add to your health log
          </Text>
          <Text style={styles.subtitle}>
            Choose an entry type. Values and units are optional where shown.
          </Text>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Open Today"
            onPress={() => router.push("/today")}
            style={styles.navButton}
          >
            <Text style={styles.navText}>Today</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Log a custom tracker entry"
            onPress={() => router.push("/planning/log-tracker")}
            style={styles.navButton}
          >
            <Text style={styles.navText}>Log a custom tracker</Text>
          </Pressable>
        </View>

        <View
          accessibilityLabel="Choose daily entry type"
          style={styles.choices}
        >
          {DAILY_DOMAINS.map((entry) => (
            <Pressable
              key={entry.value}
              accessibilityRole="radio"
              accessibilityLabel={`Add ${entry.label}`}
              accessibilityState={{
                checked: domain === entry.value,
                disabled: hasUncertainSave,
              }}
              disabled={hasUncertainSave}
              onPress={() => setDomain(entry.value)}
              style={[
                styles.choice,
                domain === entry.value && styles.selected,
                hasUncertainSave && styles.disabled,
              ]}
            >
              <Text
                style={[
                  styles.choiceText,
                  domain === entry.value && styles.selectedText,
                ]}
              >
                {entry.label}
              </Text>
            </Pressable>
          ))}
        </View>

        {hasUncertainSave && pending ? (
          <View style={styles.notice}>
            <Text style={styles.noticeText}>
              An earlier{" "}
              {DAILY_DOMAINS.find(
                (entry) => entry.value === pending.domain,
              )?.label.toLowerCase()}{" "}
              save needs recovery. Retry the original request to confirm its
              result.
            </Text>
          </View>
        ) : null}

        <DailyEntryForm
          key={domain}
          domain={domain}
          initialDraft={pending?.draft}
          submitLabel="Save entry"
          onCancel={() => router.back()}
          onCreate={create}
          onRetryUncertain={hasUncertainSave ? retryOriginalSave : undefined}
        />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { backgroundColor: "#f7f9f7", flex: 1 },
  page: { gap: 18, paddingBottom: 36 },
  header: { gap: 12, padding: 20, paddingBottom: 0 },
  title: { color: "#17201c", fontSize: 28, fontWeight: "700" },
  subtitle: { color: "#46534d", fontSize: 16, lineHeight: 23 },
  choices: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    paddingHorizontal: 20,
  },
  choice: {
    alignItems: "center",
    backgroundColor: "#fff",
    borderColor: "#68786f",
    borderRadius: 22,
    borderWidth: 1,
    justifyContent: "center",
    minHeight: 48,
    paddingHorizontal: 15,
  },
  selected: {
    backgroundColor: "#dcefe4",
    borderColor: "#245d3a",
    borderWidth: 2,
  },
  choiceText: { color: "#24342b", fontSize: 15, fontWeight: "600" },
  selectedText: { color: "#17492b" },
  disabled: { opacity: 0.55 },
  navButton: {
    alignSelf: "flex-start",
    backgroundColor: "#fff",
    borderColor: "#52645a",
    borderRadius: 12,
    borderWidth: 1,
    justifyContent: "center",
    minHeight: 48,
    paddingHorizontal: 18,
  },
  navText: { color: "#24342b", fontSize: 16, fontWeight: "700" },
  notice: {
    backgroundColor: "#fff8df",
    borderRadius: 12,
    marginHorizontal: 20,
    padding: 14,
  },
  noticeText: { color: "#4f421e", fontSize: 15, lineHeight: 22 },
});
