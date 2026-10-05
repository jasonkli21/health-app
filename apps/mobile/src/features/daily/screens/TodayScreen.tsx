import { useCallback, useRef, useState } from "react";
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";

import { dailyApi, dailyErrorMessage } from "../api";
import { planningApi, planningErrorMessage } from "../../planning/api";
import {
  DAILY_DOMAINS,
  DEVICE_TIMEZONE,
  itemTimeLabel,
  itemTitle,
  itemValue,
  localCalendarDate,
  metricLabel,
  summaryPresentation,
  type DailyItem,
} from "../model";
import {
  ActionButton,
  LoadingMessage,
  StatusMessage,
} from "../../profile/components/Ui";
import { RequestScope, requestNextPage } from "../../profile/requestScope";
import type { components } from "@personal-health/api-client";
import {
  canLoadTodayPage,
  pageMatchesTodaySnapshot,
  type TodaySnapshotIdentity,
} from "../todayPaging";

const PAGE_SIZE = 50;
type TodayResult = components["schemas"]["TodayResponse"];

function itemKindLabel(item: DailyItem): string {
  if (item.object_type === "event") {
    switch (item.event.payload.kind) {
      case "meal":
        return "Meal";
      case "workout":
        return "Workout";
      case "sleep":
        return "Sleep";
      case "symptom":
        return "Symptom";
    }
  }
  return item.observation.payload.value.metric === "custom"
    ? "Custom tracker"
    : "Observation";
}

export default function TodayScreen() {
  const router = useRouter();
  const [dateInput, setDateInput] = useState(localCalendarDate());
  const [timezoneInput, setTimezoneInput] = useState(DEVICE_TIMEZONE);
  const [date, setDate] = useState(dateInput);
  const [timezone, setTimezone] = useState(timezoneInput);
  const [data, setData] = useState<TodayResult | null>(null);
  const [items, setItems] = useState<DailyItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [occurrenceLinks, setOccurrenceLinks] = useState<
    Record<string, string>
  >({});
  const [linkPickerKey, setLinkPickerKey] = useState<string | null>(null);
  const [visibleResultScopeKey, setVisibleResultScopeKey] = useState<
    string | null
  >(null);
  const requestScope = useRef(new RequestScope());
  const [visibleSnapshot, setVisibleSnapshot] =
    useState<TodaySnapshotIdentity | null>(null);
  const queryWithResult = useRef<string | null>(null);
  const queryKey = `${date}:${timezone}`;
  const scopeKey = `today:${queryKey}:${refresh}`;

  useFocusEffect(
    useCallback(() => {
      const scope = requestScope.current.start(scopeKey);
      if (queryWithResult.current !== queryKey) {
        setData(null);
        setItems([]);
        setStale(false);
        setVisibleSnapshot(null);
        setVisibleResultScopeKey(null);
      }
      setLoading(true);
      setError(null);
      setLoadingMore(false);
      void (async () => {
        try {
          const result = await dailyApi.getToday({
            date,
            timezone,
            limit: PAGE_SIZE,
          });
          if (!requestScope.current.isCurrent(scope)) return;
          setData(result);
          setItems(result.items);
          setVisibleSnapshot({
            scopeKey,
            date: result.date,
            timezone: result.timezone,
            asOfSequence: result.as_of_sequence,
          });
          setVisibleResultScopeKey(scopeKey);
          queryWithResult.current = queryKey;
          setStale(false);
        } catch (requestError) {
          if (requestScope.current.isCurrent(scope)) {
            setError(dailyErrorMessage(requestError));
            setStale(queryWithResult.current === queryKey);
          }
        } finally {
          if (requestScope.current.isCurrent(scope)) setLoading(false);
        }
      })();
      return () => requestScope.current.invalidate(scope);
      // Retry reuses the same day and preserves its in-memory result while fetching.
      // eslint-disable-next-line react-hooks/exhaustive-deps -- refresh is an effect trigger.
    }, [date, timezone, refresh, scopeKey, queryKey]),
  );

  async function loadMore() {
    if (
      !data?.next_cursor ||
      !canLoadTodayPage({
        hasCursor: Boolean(data.next_cursor),
        loading,
        visible: visibleSnapshot,
        scopeKey,
        date,
        timezone,
        asOfSequence: data.as_of_sequence,
      })
    ) {
      return;
    }
    const scope = requestScope.current.tokenFor(scopeKey);
    if (!scope) return;
    const cursor = data.next_cursor;
    await requestNextPage(
      requestScope.current,
      scope,
      cursor,
      () => dailyApi.getToday({ date, timezone, limit: PAGE_SIZE, cursor }),
      {
        onStart: () => {
          setLoadingMore(true);
          setError(null);
        },
        onSuccess: (page) => {
          if (!pageMatchesTodaySnapshot(page, visibleSnapshot, scopeKey)) {
            setError(
              "The timeline page belongs to a different Today snapshot. Refresh and retry.",
            );
            setStale(true);
            return;
          }
          setItems((current) => [...current, ...page.items]);
          setData((current) =>
            current
              ? {
                  ...page,
                  items: current.items,
                  profile_context_refs: current.profile_context_refs,
                  profile_context_truncated: current.profile_context_truncated,
                  includes_profile_context: current.includes_profile_context,
                  plan_items: current.plan_items,
                  active_contexts: current.active_contexts,
                }
              : page,
          );
        },
        onError: (requestError) => {
          setError(dailyErrorMessage(requestError));
          setStale(true);
        },
        onFinish: () => setLoadingMore(false),
      },
    );
  }

  async function updateOccurrence(
    key: string,
    scheduleRevision: number,
    overrideRevision: number | null,
    state: "completed" | "skipped",
    linkedRecord?: DailyItem,
  ) {
    try {
      await planningApi.updatePlanOccurrence(
        { occurrence_key: key },
        {
          expected_schedule_revision: scheduleRevision,
          expected_override_revision: overrideRevision,
          state,
          linked_event_id:
            linkedRecord?.object_type === "event" ? linkedRecord.id : null,
          linked_observation_id:
            linkedRecord?.object_type === "observation"
              ? linkedRecord.id
              : null,
        },
      );
      setRefresh((value) => value + 1);
    } catch (requestError) {
      setError(planningErrorMessage(requestError));
      setRefresh((value) => value + 1);
    }
  }

  const summariesByDomain = new Map<
    string,
    components["schemas"]["MetricSummaryV1"][]
  >((data?.summaries ?? []).map((summary) => [summary.domain, []]));
  for (const summary of data?.summaries ?? []) {
    summariesByDomain.get(summary.domain)?.push(summary);
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <Text accessibilityRole="header" style={styles.title}>
            Today
          </Text>
          <Text style={styles.subtitle}>
            A sparse view of what you chose to record for one local calendar
            day.
          </Text>
          <View style={styles.nav}>
            <ActionButton
              label="Add entry"
              onPress={() => router.push("/add")}
            />
            <ActionButton
              label="Open Profile"
              secondary
              onPress={() => router.push("/profile")}
            />
            <ActionButton
              label="Open Plan"
              secondary
              onPress={() => router.push("/planning")}
            />
          </View>
        </View>

        <View style={styles.filters}>
          <Field
            label="Calendar date"
            value={dateInput}
            onChange={setDateInput}
            placeholder="YYYY-MM-DD"
          />
          <Field
            label="IANA timezone"
            value={timezoneInput}
            onChange={setTimezoneInput}
            placeholder="America/Los_Angeles"
          />
          <ActionButton
            label="Show this day"
            onPress={() => {
              setDate(dateInput.trim());
              setTimezone(timezoneInput.trim());
            }}
          />
          <ActionButton
            label="Refresh Today"
            secondary
            onPress={() => setRefresh((value) => value + 1)}
          />
        </View>

        {error && !loading ? (
          <View>
            <StatusMessage
              title={
                stale ? "Showing saved Today data" : "Today could not load"
              }
              message={stale ? `${error} The visible result is stale.` : error}
              tone="error"
            />
            <ActionButton
              label="Retry Today request"
              onPress={() => setRefresh((value) => value + 1)}
            />
          </View>
        ) : null}
        {loading && !data ? <LoadingMessage label="Loading Today" /> : null}

        {data ? (
          <View style={styles.result}>
            <Text style={styles.dayHeading}>
              {data.date} · {data.timezone}
              {stale ? " · stale" : ""}
            </Text>
            <Text style={styles.explainer}>
              These totals describe entries you logged. Missing values are not
              treated as zero or as proof that something did not happen.
            </Text>

            <View style={styles.section}>
              <Text accessibilityRole="header" style={styles.sectionTitle}>
                Daily summaries
              </Text>
              {DAILY_DOMAINS.map((domain) => {
                const summaries = summariesByDomain.get(domain.value) ?? [];
                return (
                  <View key={domain.value} style={styles.summaryGroup}>
                    <Text style={styles.groupTitle}>
                      {
                        {
                          nutrition: "Nutrition",
                          exercise: "Exercise",
                          sleep: "Sleep",
                          symptoms: "Symptoms",
                          measurements: "Measurements",
                        }[domain.value]
                      }
                    </Text>
                    {summaries.map((summary) => (
                      <View key={summary.metric} style={styles.summaryRow}>
                        <Text style={styles.summaryLabel}>
                          {metricLabel(summary.metric)}
                        </Text>
                        <Text style={styles.summaryValue}>
                          {summaryPresentation(summary).value}
                        </Text>
                        <Text style={styles.summaryMeta}>
                          {summaryPresentation(summary).coverage}
                        </Text>
                      </View>
                    ))}
                  </View>
                );
              })}
            </View>

            {data.includes_profile_context &&
            data.profile_context_refs.length > 0 ? (
              <View style={styles.section}>
                <Text accessibilityRole="header" style={styles.sectionTitle}>
                  Profile context for this day
                </Text>
                <Text style={styles.explainer}>
                  These are references to Profile items whose effective dates
                  overlap this day.
                </Text>
                {data.profile_context_refs.map((profile) => (
                  <Pressable
                    key={profile.id}
                    accessibilityRole="button"
                    accessibilityLabel={`Open Profile item ${profile.title}`}
                    onPress={() =>
                      router.push({
                        pathname: "/profile/[itemId]",
                        params: { itemId: profile.id },
                      })
                    }
                    style={styles.profileRef}
                  >
                    <Text style={styles.cardTitle}>{profile.title}</Text>
                    <Text style={styles.cardMeta}>Open Profile item</Text>
                  </Pressable>
                ))}
                {data.profile_context_truncated ? (
                  <Text style={styles.hint}>
                    Some Profile references are not shown.
                  </Text>
                ) : null}
              </View>
            ) : null}

            {(data.active_contexts ?? []).length > 0 ? (
              <View style={styles.section}>
                <Text accessibilityRole="header" style={styles.sectionTitle}>
                  Active contexts
                </Text>
                <Text style={styles.explainer}>
                  Temporary context is shown for relevance. It does not replace
                  Profile or change a regimen.
                </Text>
                {(data.active_contexts ?? []).map((context) => (
                  <View key={context.id} style={styles.profileRef}>
                    <Text style={styles.cardTitle}>{context.label}</Text>
                    <Text style={styles.cardMeta}>
                      {context.context_type.replaceAll("_", " ")} · priority{" "}
                      {context.priority}
                    </Text>
                    {context.notes ? (
                      <Text style={styles.cardBody}>{context.notes}</Text>
                    ) : null}
                  </View>
                ))}
              </View>
            ) : null}

            <View style={styles.section}>
              <Text accessibilityRole="header" style={styles.sectionTitle}>
                Planned items
              </Text>
              <Text style={styles.explainer}>
                These are intended schedule slots. An unmarked slot is unknown,
                not a missed activity.
              </Text>
              {(data.plan_items ?? []).length === 0 ? (
                <Text style={styles.cardMeta}>
                  No scheduled plan items for this day.
                </Text>
              ) : (
                (data.plan_items ?? []).map((occurrence) => (
                  <View key={occurrence.key} style={styles.timelineItem}>
                    <Text style={styles.kind}>{occurrence.state}</Text>
                    <Text style={styles.cardTitle}>{occurrence.label}</Text>
                    <Text style={styles.cardMeta}>
                      {occurrence.original_local_date}{" "}
                      {occurrence.original_local_time} · {occurrence.timezone}
                      {occurrence.dst_resolution === "exact"
                        ? ""
                        : ` · ${occurrence.dst_resolution.replaceAll("_", " ")}`}
                    </Text>
                    {occurrence.state === "rescheduled" ? (
                      <Text style={styles.cardMeta}>
                        New due time: {occurrence.due_at}
                      </Text>
                    ) : null}
                    {occurrence.linked_event_id ||
                    occurrence.linked_observation_id ? (
                      <Text style={styles.cardMeta}>
                        Linked record:{" "}
                        {occurrence.linked_event_id ??
                          occurrence.linked_observation_id}
                      </Text>
                    ) : null}
                    <ActionButton
                      label={
                        occurrenceLinks[occurrence.key]
                          ? "Change linked record"
                          : "Associate existing record"
                      }
                      secondary
                      onPress={() =>
                        setLinkPickerKey((current) =>
                          current === occurrence.key ? null : occurrence.key,
                        )
                      }
                    />
                    {linkPickerKey === occurrence.key ? (
                      <View style={styles.linkChoices}>
                        <Text style={styles.cardMeta}>
                          Optional link to an Event or Observation already shown
                          in Today
                        </Text>
                        <Pressable
                          accessibilityRole="button"
                          accessibilityState={{
                            selected: !occurrenceLinks[occurrence.key],
                          }}
                          onPress={() =>
                            setOccurrenceLinks((current) => {
                              const next = { ...current };
                              delete next[occurrence.key];
                              return next;
                            })
                          }
                          style={styles.profileRef}
                        >
                          <Text style={styles.cardMeta}>No linked record</Text>
                        </Pressable>
                        {items.map((record) => (
                          <Pressable
                            key={record.id}
                            accessibilityRole="button"
                            accessibilityState={{
                              selected:
                                occurrenceLinks[occurrence.key] === record.id,
                            }}
                            onPress={() => {
                              setOccurrenceLinks((current) => ({
                                ...current,
                                [occurrence.key]: record.id,
                              }));
                              setLinkPickerKey(null);
                            }}
                            style={styles.profileRef}
                          >
                            <Text style={styles.cardTitle}>
                              {itemTitle(record)}
                            </Text>
                            <Text style={styles.cardMeta}>
                              {record.object_type} ·{" "}
                              {itemTimeLabel(record, timezone)}
                            </Text>
                          </Pressable>
                        ))}
                        {items.length === 0 ? (
                          <Text style={styles.cardMeta}>
                            No existing records are loaded for this day.
                          </Text>
                        ) : null}
                      </View>
                    ) : null}
                    <View style={styles.nav}>
                      <ActionButton
                        label="Mark complete"
                        secondary
                        onPress={() =>
                          void updateOccurrence(
                            occurrence.key,
                            occurrence.schedule_revision,
                            occurrence.override_revision,
                            "completed",
                            items.find(
                              (record) =>
                                record.id === occurrenceLinks[occurrence.key],
                            ),
                          )
                        }
                      />
                      <ActionButton
                        label="Mark skipped"
                        secondary
                        onPress={() =>
                          void updateOccurrence(
                            occurrence.key,
                            occurrence.schedule_revision,
                            occurrence.override_revision,
                            "skipped",
                            items.find(
                              (record) =>
                                record.id === occurrenceLinks[occurrence.key],
                            ),
                          )
                        }
                      />
                      {occurrence.state !== "unknown" ? (
                        <ActionButton
                          label="View action history"
                          secondary
                          onPress={() =>
                            router.push({
                              pathname: "/planning/occurrence-history",
                              params: { key: occurrence.key },
                            })
                          }
                        />
                      ) : null}
                      <ActionButton
                        label="Reschedule"
                        secondary
                        onPress={() =>
                          router.push({
                            pathname: "/planning/reschedule",
                            params: {
                              key: occurrence.key,
                              scheduleRevision: String(
                                occurrence.schedule_revision,
                              ),
                              overrideRevision: occurrence.override_revision
                                ? String(occurrence.override_revision)
                                : "",
                              timezone: occurrence.timezone,
                              dueAt: occurrence.due_at,
                            },
                          })
                        }
                      />
                    </View>
                  </View>
                ))
              )}
            </View>

            <View style={styles.section}>
              <Text accessibilityRole="header" style={styles.sectionTitle}>
                Timeline
              </Text>
              {items.length === 0 ? (
                <View style={styles.empty}>
                  <Text style={styles.cardTitle}>
                    Nothing logged for this day
                  </Text>
                  <Text style={styles.explainer}>
                    An empty day means no entries were recorded here.
                  </Text>
                  <ActionButton
                    label="Add your first entry"
                    onPress={() => router.push("/add")}
                  />
                </View>
              ) : (
                items.map((item) => (
                  <Pressable
                    key={`${item.object_type}:${item.id}`}
                    accessibilityRole="button"
                    accessibilityLabel={`${itemKindLabel(item)}. ${itemTitle(item)}. ${itemValue(item)}. ${itemTimeLabel(item, data.timezone)}`}
                    accessibilityHint="Open this entry to review, edit, archive, or view its history."
                    onPress={() =>
                      router.push({
                        pathname: "/daily/item/[itemId]",
                        params: { itemId: item.id, type: item.object_type },
                      })
                    }
                    style={styles.timelineItem}
                  >
                    <Text style={styles.kind}>{itemKindLabel(item)}</Text>
                    <Text style={styles.cardTitle}>{itemTitle(item)}</Text>
                    <Text style={styles.cardBody}>{itemValue(item)}</Text>
                    <Text style={styles.cardMeta}>
                      {itemTimeLabel(item, data.timezone)}
                    </Text>
                  </Pressable>
                ))
              )}
              {data.next_cursor ? (
                <ActionButton
                  label="Load more timeline entries"
                  onPress={() => void loadMore()}
                  busy={loadingMore}
                  disabled={
                    loadingMore ||
                    visibleResultScopeKey !== scopeKey ||
                    !canLoadTodayPage({
                      hasCursor: Boolean(data.next_cursor),
                      loading,
                      visible: visibleSnapshot,
                      scopeKey,
                      date,
                      timezone,
                      asOfSequence: data.as_of_sequence,
                    })
                  }
                  secondary
                />
              ) : null}
            </View>
          </View>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}) {
  return (
    <View style={styles.filterField}>
      <Text style={styles.filterLabel}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        value={value}
        onChangeText={onChange}
        placeholder={placeholder}
        autoCapitalize="none"
        style={styles.input}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  safeArea: { backgroundColor: "#f7f9f7", flex: 1 },
  content: { gap: 18, padding: 20, paddingBottom: 36 },
  header: { gap: 12 },
  title: { color: "#17201c", fontSize: 30, fontWeight: "700" },
  subtitle: { color: "#46534d", fontSize: 16, lineHeight: 23 },
  nav: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  filters: {
    backgroundColor: "#eaf0ec",
    borderRadius: 14,
    gap: 12,
    padding: 16,
  },
  filterField: { gap: 6 },
  filterLabel: { color: "#203a2e", fontSize: 15, fontWeight: "700" },
  input: {
    backgroundColor: "#fff",
    borderColor: "#68786f",
    borderRadius: 10,
    borderWidth: 1,
    color: "#17201c",
    fontSize: 16,
    minHeight: 50,
    paddingHorizontal: 14,
  },
  result: { gap: 16 },
  dayHeading: { color: "#203a2e", fontSize: 19, fontWeight: "700" },
  explainer: { color: "#46534d", fontSize: 14, lineHeight: 20 },
  section: { gap: 10 },
  sectionTitle: { color: "#203a2e", fontSize: 22, fontWeight: "700" },
  summaryGroup: {
    backgroundColor: "#fff",
    borderColor: "#c8d2cb",
    borderRadius: 14,
    borderWidth: 1,
    gap: 8,
    padding: 14,
  },
  groupTitle: { color: "#245d3a", fontSize: 17, fontWeight: "700" },
  summaryRow: {
    borderTopColor: "#e0e6e2",
    borderTopWidth: 1,
    gap: 2,
    paddingTop: 8,
  },
  summaryLabel: { color: "#24342b", fontSize: 15, fontWeight: "600" },
  summaryValue: { color: "#17201c", fontSize: 18, fontWeight: "700" },
  summaryMeta: { color: "#596860", fontSize: 13 },
  timelineItem: {
    backgroundColor: "#fff",
    borderColor: "#c8d2cb",
    borderRadius: 14,
    borderWidth: 1,
    gap: 5,
    minHeight: 92,
    padding: 15,
  },
  kind: {
    color: "#245d3a",
    fontSize: 13,
    fontWeight: "700",
    textTransform: "uppercase",
  },
  cardTitle: { color: "#17201c", fontSize: 17, fontWeight: "700" },
  cardBody: { color: "#34463b", fontSize: 15, lineHeight: 21 },
  cardMeta: { color: "#596860", fontSize: 13 },
  profileRef: {
    backgroundColor: "#fff",
    borderColor: "#c8d2cb",
    borderRadius: 12,
    borderWidth: 1,
    gap: 4,
    minHeight: 66,
    padding: 14,
  },
  linkChoices: { gap: 8, paddingLeft: 8 },
  empty: {
    alignItems: "flex-start",
    backgroundColor: "#fff",
    borderRadius: 14,
    gap: 10,
    padding: 16,
  },
  hint: { color: "#4d5a54", fontSize: 14, lineHeight: 20 },
});
