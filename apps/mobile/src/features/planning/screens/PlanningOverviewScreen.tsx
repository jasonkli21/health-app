import { useEffect, useState } from "react";
import { Link, useRouter } from "expo-router";
import {
  Alert,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import type { components } from "@personal-health/api-client";

import {
  ActionButton,
  LoadingMessage,
  StatusMessage,
} from "../../profile/components/Ui";
import { planningApi, planningErrorMessage } from "../api";
import type { PlanningItem } from "../api";

const GROUPS: { kind: string; label: string; add: boolean }[] = [
  { kind: "goal", label: "Goals", add: true },
  { kind: "regimen", label: "Regimens", add: true },
  { kind: "plan", label: "Plans", add: true },
  { kind: "context", label: "Contexts", add: true },
  { kind: "tracker_definition", label: "Custom trackers", add: true },
];

export default function PlanningOverviewScreen() {
  const router = useRouter();
  const [items, setItems] = useState<PlanningItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refresh, setRefresh] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    Promise.all([
      planningApi.listGoals({ limit: 100 }),
      planningApi.listRegimens({ limit: 100 }),
      planningApi.listPlans({ limit: 100 }),
      planningApi.listContexts({ limit: 100 }),
      planningApi.listTrackers({ limit: 100 }),
    ])
      .then((pages) => {
        if (current) {
          setItems(pages.flatMap((page) => page.items));
          setError(null);
        }
      })
      .catch((requestError: unknown) => {
        if (current) setError(planningErrorMessage(requestError));
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, [refresh]);

  async function archive(item: PlanningItem) {
    setBusyId(item.id);
    try {
      const query = { expected_revision: item.revision };
      let archived: PlanningItem;
      if (item.object_type === "goal")
        archived = await planningApi.archiveGoal({ goal_id: item.id }, query);
      else if (item.object_type === "regimen")
        archived = await planningApi.archiveRegimen(
          { regimen_id: item.id },
          query,
        );
      else if (item.object_type === "plan")
        archived = await planningApi.archivePlan({ plan_id: item.id }, query);
      else if (item.object_type === "context")
        archived = await planningApi.archiveContext(
          { context_id: item.id },
          query,
        );
      else
        archived = await planningApi.archiveTracker(
          { tracker_id: item.id },
          query,
        );
      setRefresh((value) => value + 1);
      router.push({
        pathname: "/planning/[kind]/[id]",
        params: { kind: archived.object_type, id: archived.id },
      });
    } catch (requestError) {
      setError(planningErrorMessage(requestError));
    } finally {
      setBusyId(null);
    }
  }

  async function transition(item: PlanningItem, lifecycle: string) {
    setBusyId(item.id);
    try {
      const expected_revision = item.revision;
      if (item.object_type === "goal")
        await planningApi.transitionGoal(
          { goal_id: item.id },
          {
            expected_revision,
            lifecycle: lifecycle as components["schemas"]["GoalLifecycle"],
          },
        );
      else if (item.object_type === "regimen")
        await planningApi.transitionRegimen(
          { regimen_id: item.id },
          {
            expected_revision,
            lifecycle: lifecycle as components["schemas"]["RegimenLifecycle"],
          },
        );
      else if (item.object_type === "plan")
        await planningApi.transitionPlan(
          { plan_id: item.id },
          {
            expected_revision,
            lifecycle: lifecycle as components["schemas"]["PlanLifecycle"],
          },
        );
      else if (item.object_type === "context")
        await planningApi.transitionContext(
          { context_id: item.id },
          {
            expected_revision,
            lifecycle: lifecycle as components["schemas"]["ContextLifecycle"],
          },
        );
      setRefresh((value) => value + 1);
    } catch (requestError) {
      setError(planningErrorMessage(requestError));
    } finally {
      setBusyId(null);
    }
  }

  const visible = items.filter((item) => item.status === "active");
  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <Text accessibilityRole="header" style={styles.title}>
            Plan
          </Text>
          <Text style={styles.subtitle}>
            Organize goals and intended routines. A plan item is not a record
            that an activity happened.
          </Text>
          <View style={styles.actions}>
            <ActionButton
              label="Open Today"
              onPress={() => router.push("/today")}
              secondary
            />
            <ActionButton
              label="Add a tracker entry"
              onPress={() => router.push("/planning/log-tracker")}
            />
          </View>
          <View style={styles.actions}>
            <Link href="/profile" style={styles.link}>
              Profile
            </Link>
            <Link href="/add" style={styles.link}>
              Add an entry
            </Link>
          </View>
        </View>

        {error ? (
          <StatusMessage
            title="Planning could not load"
            message={error}
            tone="error"
          />
        ) : null}
        {loading && items.length === 0 ? (
          <LoadingMessage label="Loading Plan" />
        ) : null}
        {!loading && !error && visible.length === 0 ? (
          <View style={styles.empty}>
            <Text style={styles.cardTitle}>No planning items yet</Text>
            <Text style={styles.body}>
              Create a goal, routine, plan, temporary context, or custom
              tracker.
            </Text>
          </View>
        ) : null}

        {GROUPS.map((group) => {
          const groupItems = visible.filter(
            (item) =>
              item.object_type === group.kind &&
              (group.kind !== "context" || item.lifecycle === "active"),
          );
          return (
            <View key={group.kind} style={styles.section}>
              <View style={styles.sectionHeader}>
                <Text accessibilityRole="header" style={styles.sectionTitle}>
                  {group.label}
                </Text>
                {group.add ? (
                  <ActionButton
                    label={`Add ${group.label.replace(/s$/, "").replace("Active context", "context").replace("Custom tracker", "tracker")}`}
                    secondary
                    onPress={() =>
                      router.push({
                        pathname: "/planning/new",
                        params: { kind: group.kind },
                      })
                    }
                  />
                ) : null}
              </View>
              {groupItems.map((item) => (
                <View key={item.id} style={styles.card}>
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel={`Open ${item.title}, ${item.lifecycle}`}
                    onPress={() =>
                      router.push({
                        pathname: "/planning/[kind]/[id]",
                        params: { kind: item.object_type, id: item.id },
                      })
                    }
                    style={styles.cardMain}
                  >
                    <Text style={styles.cardTitle}>{item.title}</Text>
                    <Text style={styles.body}>
                      {item.lifecycle} · revision {item.revision}
                    </Text>
                    <Text style={styles.meta}>{summary(item)}</Text>
                  </Pressable>
                  {item.object_type === "goal" ||
                  item.object_type === "regimen" ||
                  item.object_type === "plan" ? (
                    <View style={styles.actions}>
                      {item.lifecycle === "active" ? (
                        <ActionButton
                          label="Pause"
                          secondary
                          busy={busyId === item.id}
                          onPress={() => void transition(item, "paused")}
                        />
                      ) : item.lifecycle === "paused" ? (
                        <ActionButton
                          label="Resume"
                          secondary
                          busy={busyId === item.id}
                          onPress={() => void transition(item, "active")}
                        />
                      ) : null}
                      {item.lifecycle !== "completed" ? (
                        <ActionButton
                          label="Complete"
                          secondary
                          busy={busyId === item.id}
                          onPress={() => void transition(item, "completed")}
                        />
                      ) : null}
                    </View>
                  ) : item.object_type === "context" &&
                    item.lifecycle === "active" ? (
                    <ActionButton
                      label="End context"
                      secondary
                      busy={busyId === item.id}
                      onPress={() => void transition(item, "ended")}
                    />
                  ) : null}
                  <ActionButton
                    label="Archive"
                    secondary
                    busy={busyId === item.id}
                    onPress={() =>
                      Alert.alert(
                        "Archive this item?",
                        "It will remain available in history.",
                        [
                          { text: "Cancel", style: "cancel" },
                          {
                            text: "Archive",
                            style: "destructive",
                            onPress: () => void archive(item),
                          },
                        ],
                      )
                    }
                  />
                </View>
              ))}
            </View>
          );
        })}
        <ActionButton
          label="Refresh planning"
          secondary
          onPress={() => setRefresh((value) => value + 1)}
        />
      </ScrollView>
    </SafeAreaView>
  );
}

function summary(item: PlanningItem): string {
  if (item.object_type === "goal")
    return `${item.goal.domain}${item.goal.target ? ` · target ${item.goal.target.value} ${item.goal.target.unit}` : " · progress not estimated"}`;
  if (item.object_type === "regimen")
    return `${item.regimen.kind} · ${item.regimen.domain}`;
  if (item.object_type === "plan")
    return `${item.plan.items?.length ?? 0} plan items`;
  if (item.object_type === "context") {
    const validity = [
      item.context.start_at ? `from ${item.context.start_at}` : null,
      item.context.end_at ? `until ${item.context.end_at} (exclusive)` : null,
    ]
      .filter(Boolean)
      .join(" · ");
    return `${item.context.context_type} · priority ${item.context.priority ?? 0}${validity ? ` · ${validity}` : ""}`;
  }
  return `${item.definition.domain} · schema v${item.current_schema_version}`;
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: "#f7f9f7" },
  content: { gap: 20, padding: 20, paddingBottom: 36 },
  header: { gap: 12 },
  title: { color: "#17201c", fontSize: 30, fontWeight: "700" },
  subtitle: { color: "#46534d", fontSize: 16, lineHeight: 23 },
  section: { gap: 10 },
  sectionHeader: {
    alignItems: "center",
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10,
    justifyContent: "space-between",
  },
  sectionTitle: { color: "#203a2e", fontSize: 22, fontWeight: "700" },
  card: {
    backgroundColor: "#fff",
    borderColor: "#c8d2cb",
    borderRadius: 14,
    borderWidth: 1,
    gap: 10,
    padding: 14,
  },
  cardMain: { gap: 4 },
  cardTitle: { color: "#17201c", fontSize: 18, fontWeight: "700" },
  body: { color: "#46534d", fontSize: 14, lineHeight: 20 },
  meta: { color: "#596860", fontSize: 13 },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  link: {
    color: "#245d3a",
    fontSize: 16,
    fontWeight: "700",
    paddingVertical: 10,
  },
  empty: { backgroundColor: "#fff", borderRadius: 14, gap: 8, padding: 18 },
});
