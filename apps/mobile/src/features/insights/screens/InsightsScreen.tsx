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
import { ApiError } from "@personal-health/api-client";
import type { components } from "@personal-health/api-client";

import { sessionStore } from "../../../auth/sessionStore";
import {
  localCalendarDate,
  newDailyId,
  DEVICE_TIMEZONE,
} from "../../daily/model";
import {
  ActionButton,
  LoadingMessage,
  StatusMessage,
} from "../../profile/components/Ui";
import { insightsApi, insightsErrorMessage } from "../api";

type Metric = components["schemas"]["MetricDefinition"];
type Pair = components["schemas"]["AssociationPair"];
type Trend = components["schemas"]["StoredTrendResponse"];
type Association = components["schemas"]["StoredAssociationResponse"];
type Insight = components["schemas"]["InsightResponse"];
type Recommendation = components["schemas"]["RecommendationResponse"];
type Experiment = components["schemas"]["ExperimentResponse"];
type ExperimentResult = components["schemas"]["ExperimentResult"];
type ExperimentDraft = components["schemas"]["ExperimentPayloadV1"];
type PendingExperimentCreate = { id: string; experiment: ExperimentDraft };
type EvidenceLink = {
  object_id: string;
  revision: number;
  object_type: string;
};

function isDefinitiveCreateFailure(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    [400, 401, 403, 404, 409, 413, 415, 422].includes(error.status)
  );
}

function dateOffset(days: number): string {
  const value = new Date();
  value.setDate(value.getDate() + days);
  return localCalendarDate(value);
}

function newExperimentId(): string {
  return newDailyId();
}

function ValueField({
  label,
  value,
  onChange,
  placeholder,
  multiline = false,
  keyboardType = "default",
  disabled = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  multiline?: boolean;
  keyboardType?: "default" | "numeric";
  disabled?: boolean;
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        value={value}
        onChangeText={onChange}
        placeholder={placeholder}
        multiline={multiline}
        editable={!disabled}
        keyboardType={keyboardType}
        autoCapitalize={multiline ? "sentences" : "none"}
        style={[styles.input, multiline && styles.multiline]}
      />
    </View>
  );
}

function SelectButton({
  label,
  selected,
  onPress,
  disabled = false,
}: {
  label: string;
  selected: boolean;
  onPress: () => void;
  disabled?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      disabled={disabled}
      onPress={onPress}
      style={[styles.choice, selected && styles.choiceSelected]}
    >
      <Text style={[styles.choiceText, selected && styles.choiceTextSelected]}>
        {label}
      </Text>
    </Pressable>
  );
}

function fmt(value: number | null, unit: string): string {
  return value === null
    ? "No known values"
    : `${Number(value.toFixed(2))} ${unit}`;
}

function newExperimentDraft(
  metric: string,
): components["schemas"]["ExperimentPayloadV1"] {
  return {
    hypothesis: "",
    intervention: "",
    outcome_metric: metric,
    baseline_start: dateOffset(-20),
    start_date: dateOffset(-10),
    end_date: localCalendarDate(),
    status: "draft",
    notes: "",
  };
}

export default function InsightsScreen() {
  const router = useRouter();
  const today = localCalendarDate();
  const [metrics, setMetrics] = useState<Metric[]>([]);
  const [pairs, setPairs] = useState<Pair[]>([]);
  const [insights, setInsights] = useState<Insight[]>([]);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [insightCursor, setInsightCursor] = useState<string | null>(null);
  const [recommendationCursor, setRecommendationCursor] = useState<
    string | null
  >(null);
  const [experimentCursor, setExperimentCursor] = useState<string | null>(null);
  const [expandedEvidence, setExpandedEvidence] = useState<
    Record<string, boolean>
  >({});
  const [metric, setMetric] = useState("");
  const [selectedPairs, setSelectedPairs] = useState<string[]>([]);
  const [from, setFrom] = useState(dateOffset(-29));
  const [to, setTo] = useState(today);
  const [timezone, setTimezone] = useState(DEVICE_TIMEZONE);
  const [trend, setTrend] = useState<Trend | null>(null);
  const [associations, setAssociations] = useState<Association[]>([]);
  const [results, setResults] = useState<Record<string, ExperimentResult>>({});
  const [form, setForm] = useState<
    components["schemas"]["ExperimentPayloadV1"]
  >(newExperimentDraft(""));
  const [editing, setEditing] = useState<Experiment | null>(null);
  const [pendingCreate, setPendingCreate] =
    useState<PendingExperimentCreate | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const screenGeneration = useRef(0);

  useFocusEffect(
    useCallback(() => {
      let active = true;
      screenGeneration.current += 1;
      const epoch = sessionStore.getSnapshot().epoch;
      setLoading(true);
      setBusy(false);
      setError(null);
      setTrend(null);
      setAssociations([]);
      setResults({});
      void Promise.all([
        insightsApi.listAnalyticsMetrics(),
        insightsApi.listAnalyticsAssociationPairs(),
        insightsApi.listInsights({ limit: 50 }),
        insightsApi.listRecommendations({ limit: 50 }),
        insightsApi.listExperiments({ limit: 50 }),
      ])
        .then(
          ([
            catalog,
            pairCatalog,
            insightPage,
            recommendationPage,
            experimentPage,
          ]) => {
            if (!active || sessionStore.getSnapshot().epoch !== epoch) return;
            setMetrics(catalog.items);
            setPairs(pairCatalog.items);
            setInsights(insightPage.items);
            setRecommendations(recommendationPage.items);
            setExperiments(experimentPage.items);
            setInsightCursor(insightPage.next_cursor);
            setRecommendationCursor(recommendationPage.next_cursor);
            setExperimentCursor(experimentPage.next_cursor);
            setMetric((current) => current || catalog.items[0]?.metric || "");
            setForm((current) =>
              current.outcome_metric
                ? current
                : newExperimentDraft(catalog.items[0]?.metric || ""),
            );
          },
        )
        .catch((requestError: unknown) => {
          if (active && sessionStore.getSnapshot().epoch === epoch)
            setError(insightsErrorMessage(requestError));
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

  async function runTrend() {
    if (!metric) return;
    const generation = screenGeneration.current;
    const epoch = sessionStore.getSnapshot().epoch;
    setBusy(true);
    setError(null);
    try {
      const result = await insightsApi.getTrend({ metric, from, to, timezone });
      if (
        generation === screenGeneration.current &&
        epoch === sessionStore.getSnapshot().epoch
      )
        setTrend(result);
    } catch (requestError) {
      if (
        generation === screenGeneration.current &&
        epoch === sessionStore.getSnapshot().epoch
      )
        setError(insightsErrorMessage(requestError));
    } finally {
      if (
        generation === screenGeneration.current &&
        epoch === sessionStore.getSnapshot().epoch
      )
        setBusy(false);
    }
  }

  async function runAssociations() {
    if (!selectedPairs.length) return;
    const generation = screenGeneration.current;
    const epoch = sessionStore.getSnapshot().epoch;
    setBusy(true);
    setError(null);
    try {
      const response = await insightsApi.getAssociations({
        pair: selectedPairs,
        from,
        to,
        timezone,
      });
      if (
        generation === screenGeneration.current &&
        epoch === sessionStore.getSnapshot().epoch
      )
        setAssociations(response);
    } catch (requestError) {
      if (
        generation === screenGeneration.current &&
        epoch === sessionStore.getSnapshot().epoch
      )
        setError(insightsErrorMessage(requestError));
    } finally {
      if (
        generation === screenGeneration.current &&
        epoch === sessionStore.getSnapshot().epoch
      )
        setBusy(false);
    }
  }

  async function generateInsights() {
    if (!metric && !selectedPairs.length) return;
    const generation = screenGeneration.current;
    const epoch = sessionStore.getSnapshot().epoch;
    setBusy(true);
    setError(null);
    try {
      const generated = await insightsApi.refreshInsights({
        metrics: metric ? [metric] : [],
        association_pairs: selectedPairs,
        from_date: from,
        to_date: to,
        timezone,
      });
      const [insightPage, recommendationPage] = await Promise.all([
        insightsApi.listInsights({ limit: 50 }),
        insightsApi.listRecommendations({ limit: 50 }),
      ]);
      if (
        generation !== screenGeneration.current ||
        epoch !== sessionStore.getSnapshot().epoch
      )
        return;
      setTrend(generated.signals[0] ?? null);
      setAssociations(generated.associations);
      setInsights(insightPage.items);
      setRecommendations(recommendationPage.items);
      setInsightCursor(insightPage.next_cursor);
      setRecommendationCursor(recommendationPage.next_cursor);
      setResults({});
    } catch (requestError) {
      if (
        generation === screenGeneration.current &&
        epoch === sessionStore.getSnapshot().epoch
      )
        setError(insightsErrorMessage(requestError));
    } finally {
      if (
        generation === screenGeneration.current &&
        epoch === sessionStore.getSnapshot().epoch
      )
        setBusy(false);
    }
  }

  async function loadMoreInsights() {
    if (!insightCursor) return;
    const generation = screenGeneration.current;
    const epoch = sessionStore.getSnapshot().epoch;
    setBusy(true);
    setError(null);
    try {
      const page = await insightsApi.listInsights({
        limit: 50,
        cursor: insightCursor,
      });
      if (
        generation !== screenGeneration.current ||
        epoch !== sessionStore.getSnapshot().epoch
      )
        return;
      setInsights((current) => [
        ...new Map(
          [...current, ...page.items].map((item) => [item.id, item]),
        ).values(),
      ]);
      setInsightCursor(page.next_cursor);
    } catch (requestError) {
      if (
        generation === screenGeneration.current &&
        epoch === sessionStore.getSnapshot().epoch
      )
        setError(insightsErrorMessage(requestError));
    } finally {
      if (
        generation === screenGeneration.current &&
        epoch === sessionStore.getSnapshot().epoch
      )
        setBusy(false);
    }
  }

  async function loadMoreRecommendations() {
    if (!recommendationCursor) return;
    const generation = screenGeneration.current;
    const epoch = sessionStore.getSnapshot().epoch;
    setBusy(true);
    setError(null);
    try {
      const page = await insightsApi.listRecommendations({
        limit: 50,
        cursor: recommendationCursor,
      });
      if (
        generation !== screenGeneration.current ||
        epoch !== sessionStore.getSnapshot().epoch
      )
        return;
      setRecommendations((current) => [
        ...new Map(
          [...current, ...page.items].map((item) => [item.id, item]),
        ).values(),
      ]);
      setRecommendationCursor(page.next_cursor);
    } catch (requestError) {
      if (
        generation === screenGeneration.current &&
        epoch === sessionStore.getSnapshot().epoch
      )
        setError(insightsErrorMessage(requestError));
    } finally {
      if (
        generation === screenGeneration.current &&
        epoch === sessionStore.getSnapshot().epoch
      )
        setBusy(false);
    }
  }

  async function loadMoreExperiments() {
    if (!experimentCursor) return;
    const generation = screenGeneration.current;
    const epoch = sessionStore.getSnapshot().epoch;
    setBusy(true);
    setError(null);
    try {
      const page = await insightsApi.listExperiments({
        limit: 50,
        cursor: experimentCursor,
      });
      if (
        generation !== screenGeneration.current ||
        epoch !== sessionStore.getSnapshot().epoch
      )
        return;
      setExperiments((current) => [
        ...new Map(
          [...current, ...page.items].map((item) => [item.id, item]),
        ).values(),
      ]);
      setExperimentCursor(page.next_cursor);
    } catch (requestError) {
      if (
        generation === screenGeneration.current &&
        epoch === sessionStore.getSnapshot().epoch
      )
        setError(insightsErrorMessage(requestError));
    } finally {
      if (
        generation === screenGeneration.current &&
        epoch === sessionStore.getSnapshot().epoch
      )
        setBusy(false);
    }
  }

  async function changeInsight(item: Insight) {
    setBusy(true);
    setError(null);
    try {
      const updated = await insightsApi.changeInsightState(
        { insight_id: item.id },
        { expected_revision: item.revision, state: "dismissed" },
      );
      setInsights((current) =>
        current.map((row) => (row.id === updated.id ? updated : row)),
      );
    } catch (requestError) {
      setError(insightsErrorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  async function changeRecommendation(
    item: Recommendation,
    state: "accepted" | "dismissed",
  ) {
    setBusy(true);
    setError(null);
    try {
      const updated = await insightsApi.changeRecommendationState(
        { recommendation_id: item.id },
        { expected_revision: item.revision, state },
      );
      setRecommendations((current) =>
        current.map((row) => (row.id === updated.id ? updated : row)),
      );
    } catch (requestError) {
      setError(insightsErrorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  async function saveExperiment() {
    if (!form.outcome_metric) return;
    setBusy(true);
    setError(null);
    const attempt = editing
      ? null
      : (pendingCreate ?? { id: newExperimentId(), experiment: form });
    if (attempt && !pendingCreate) setPendingCreate(attempt);
    try {
      const result = editing
        ? await insightsApi.updateExperiment(
            { experiment_id: editing.id },
            { expected_revision: editing.revision, experiment: form },
          )
        : await insightsApi.createExperiment({
            id: attempt!.id,
            experiment: attempt!.experiment,
          });
      setExperiments((current) => {
        const next = new Map(current.map((item) => [item.id, item]));
        next.set(result.id, result);
        return [...next.values()].sort((left, right) =>
          right.created_at.localeCompare(left.created_at),
        );
      });
      if (!editing) setPendingCreate(null);
      setEditing(null);
      setForm(newExperimentDraft(metric));
    } catch (requestError) {
      if (!editing && isDefinitiveCreateFailure(requestError))
        setPendingCreate(null);
      setError(insightsErrorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  function editExperiment(item: Experiment) {
    setEditing(item);
    setForm(item.experiment);
  }

  async function transitionExperiment(
    item: Experiment,
    state: "active" | "completed" | "stopped" | "archived",
  ) {
    setBusy(true);
    setError(null);
    try {
      const updated = await insightsApi.changeExperimentState(
        { experiment_id: item.id },
        { expected_revision: item.revision, state },
      );
      setExperiments((current) =>
        current.map((row) => (row.id === updated.id ? updated : row)),
      );
      setResults((current) => {
        const next = { ...current };
        delete next[updated.id];
        return next;
      });
      if (editing?.id === updated.id) setEditing(updated);
    } catch (requestError) {
      setError(insightsErrorMessage(requestError));
    } finally {
      setBusy(false);
    }
  }

  async function loadExperimentResult(item: Experiment) {
    const generation = screenGeneration.current;
    const epoch = sessionStore.getSnapshot().epoch;
    setBusy(true);
    setError(null);
    try {
      const response = await insightsApi.getExperimentResults(
        { experiment_id: item.id },
        { timezone },
      );
      if (
        generation === screenGeneration.current &&
        epoch === sessionStore.getSnapshot().epoch
      )
        setResults((current) => ({ ...current, [item.id]: response.result }));
    } catch (requestError) {
      if (
        generation === screenGeneration.current &&
        epoch === sessionStore.getSnapshot().epoch
      )
        setError(insightsErrorMessage(requestError));
    } finally {
      if (
        generation === screenGeneration.current &&
        epoch === sessionStore.getSnapshot().epoch
      )
        setBusy(false);
    }
  }

  const selectedMetric = metrics.find((item) => item.metric === metric);
  const selectedOutcomeMetric = metrics.find(
    (item) => item.metric === form.outcome_metric,
  );
  const designLocked = editing !== null && editing.state !== "draft";
  const visiblePoints = trend?.result.points.slice(-14) ?? [];

  function openEvidence(reference: EvidenceLink) {
    if (reference.object_type === "derived_signal") {
      router.push({
        pathname: "/analytics/evidence/[objectId]",
        params: {
          objectId: reference.object_id,
          revision: String(reference.revision),
        },
      });
      return;
    }
    if (
      reference.object_type === "event" ||
      reference.object_type === "observation"
    ) {
      router.push({
        pathname: "/daily/item/[itemId]/history",
        params: {
          itemId: reference.object_id,
          type: reference.object_type,
          revision: String(reference.revision),
        },
      });
    }
  }

  function toggleEvidence(key: string) {
    setExpandedEvidence((current) => ({ ...current, [key]: !current[key] }));
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <Text accessibilityRole="header" style={styles.title}>
            Insights
          </Text>
          <Text style={styles.body}>
            Descriptive summaries of values you logged. Missing days stay
            visible as gaps; these results do not establish clinical meaning or
            cause.
          </Text>
        </View>

        {error ? (
          <StatusMessage
            title="Analytics request"
            message={error}
            tone="error"
          />
        ) : null}
        {loading ? <LoadingMessage label="Loading Insights" /> : null}

        {!loading ? (
          <>
            <View style={styles.section}>
              <Text accessibilityRole="header" style={styles.sectionTitle}>
                Choose a metric
              </Text>
              <Text style={styles.help}>
                Units and aggregation are shown for each supported metric.
                Tracker versions remain separate.
              </Text>
              <View style={styles.choices}>
                {metrics.map((item) => (
                  <SelectButton
                    key={item.metric}
                    label={`${item.label} · ${item.unit}`}
                    selected={metric === item.metric}
                    onPress={() => {
                      setMetric(item.metric);
                      setTrend(null);
                      setAssociations([]);
                    }}
                  />
                ))}
              </View>
              {selectedMetric ? (
                <Text style={styles.help}>{selectedMetric.aggregation}</Text>
              ) : null}
              <View style={styles.row}>
                <ValueField
                  label="From date"
                  value={from}
                  onChange={(value) => {
                    setFrom(value);
                    setTrend(null);
                    setAssociations([]);
                  }}
                  placeholder="YYYY-MM-DD"
                />
                <ValueField
                  label="To date"
                  value={to}
                  onChange={(value) => {
                    setTo(value);
                    setTrend(null);
                    setAssociations([]);
                  }}
                  placeholder="YYYY-MM-DD"
                />
              </View>
              <ValueField
                label="IANA timezone"
                value={timezone}
                onChange={(value) => {
                  setTimezone(value);
                  setTrend(null);
                  setAssociations([]);
                  setResults({});
                }}
                placeholder="America/Los_Angeles"
              />
              <ActionButton
                label="Show trend"
                busy={busy}
                disabled={!metric}
                onPress={() => void runTrend()}
              />
            </View>

            {trend ? (
              <View style={styles.section}>
                <Text accessibilityRole="header" style={styles.sectionTitle}>
                  {trend.result.label}
                </Text>
                <Text style={styles.help}>
                  {trend.result.from_date}–{trend.result.to_date} ·{" "}
                  {trend.result.timezone} · {trend.result.method_version}
                </Text>
                <Text style={styles.summary}>
                  Mean {fmt(trend.result.mean, trend.result.unit)} · median{" "}
                  {fmt(trend.result.median, trend.result.unit)}
                </Text>
                <Text style={styles.help}>
                  Coverage: {trend.result.coverage.known_days}/
                  {trend.result.coverage.calendar_days} known days;{" "}
                  {trend.result.coverage.missing_days} missing;{" "}
                  {trend.result.coverage.partial_days} partial. Seven-known-day
                  rolling means: {trend.result.rolling_7_known_day_mean.length}.
                </Text>
                {trend.result.comparison ? (
                  <Text style={styles.help}>
                    Descriptive half-window means:{" "}
                    {fmt(
                      trend.result.comparison.before.mean,
                      trend.result.unit,
                    )}{" "}
                    then{" "}
                    {fmt(trend.result.comparison.after.mean, trend.result.unit)}
                    . This is not a clinical significance estimate.
                  </Text>
                ) : (
                  <Text style={styles.help}>
                    Not enough known days in each half for a comparison.
                  </Text>
                )}
                <Text style={styles.tableHeading}>
                  Daily values · most recent 14 calendar days
                </Text>
                {visiblePoints.map((point) => (
                  <View key={point.date} style={styles.tableRow}>
                    <Text style={styles.tableDate}>{point.date}</Text>
                    <Text style={styles.tableValue}>
                      {fmt(point.value, trend.result.unit)}
                    </Text>
                    <Text style={styles.tableMeta}>
                      {point.value === null
                        ? "No known value"
                        : `${point.known_count} known${point.partial ? " · partial" : ""}`}
                    </Text>
                  </View>
                ))}
                <Text style={styles.help}>
                  {trend.result.evidence_refs.length} exact source revisions
                  support this result.
                </Text>
                {trend.result.evidence_refs
                  .slice(0, expandedEvidence.trend ? undefined : 8)
                  .map((reference) => (
                    <Pressable
                      key={`${reference.object_id}:${reference.revision}`}
                      accessibilityRole="button"
                      onPress={() => openEvidence(reference)}
                      style={styles.evidenceLink}
                    >
                      <Text style={styles.evidenceText}>
                        {reference.object_type} · revision {reference.revision}{" "}
                        · {reference.object_id}
                      </Text>
                    </Pressable>
                  ))}
                {trend.result.evidence_refs.length > 8 ? (
                  <ActionButton
                    label={
                      expandedEvidence.trend
                        ? "Show fewer source references"
                        : `Show all ${trend.result.evidence_refs.length} source references`
                    }
                    secondary
                    onPress={() => toggleEvidence("trend")}
                  />
                ) : null}
              </View>
            ) : null}

            <View style={styles.section}>
              <Text accessibilityRole="header" style={styles.sectionTitle}>
                Same-day associations
              </Text>
              <Text style={styles.help}>
                Select up to five predefined pairs. Results require at least 14
                paired days across 21 calendar days.
              </Text>
              <View style={styles.choices}>
                {pairs.map((pair) => (
                  <SelectButton
                    key={pair.id}
                    label={`${pair.first.replaceAll("_", " ")} ↔ ${pair.second.replaceAll("_", " ")}`}
                    selected={selectedPairs.includes(pair.id)}
                    onPress={() =>
                      setSelectedPairs((current) =>
                        current.includes(pair.id)
                          ? current.filter((value) => value !== pair.id)
                          : current.length < 5
                            ? [...current, pair.id]
                            : current,
                      )
                    }
                  />
                ))}
              </View>
              <ActionButton
                label="Analyze selected pairs"
                secondary
                busy={busy}
                disabled={!selectedPairs.length}
                onPress={() => void runAssociations()}
              />
              {associations.map((item) => (
                <View key={item.id} style={styles.card}>
                  <Text style={styles.cardTitle}>
                    {item.result.pair.first.replaceAll("_", " ")} and{" "}
                    {item.result.pair.second.replaceAll("_", " ")}
                  </Text>
                  <Text style={styles.cardBody}>
                    {item.result.status === "available"
                      ? `Spearman ρ ${item.result.rho?.toFixed(2)}`
                      : item.result.status.replaceAll("_", " ")}{" "}
                    · {item.result.paired_days} paired days of{" "}
                    {item.result.calendar_days} · {item.result.from_date}–
                    {item.result.to_date}
                  </Text>
                  <Text style={styles.help}>{item.result.limitation}</Text>
                </View>
              ))}
            </View>

            <View style={styles.section}>
              <Text accessibilityRole="header" style={styles.sectionTitle}>
                Evidence-linked insights
              </Text>
              <ActionButton
                label="Generate for this window"
                busy={busy}
                disabled={!metric && !selectedPairs.length}
                onPress={() => void generateInsights()}
              />
              {insights.length === 0 ? (
                <Text style={styles.help}>
                  No saved insights yet. Sparse data may have no eligible
                  insight.
                </Text>
              ) : null}
              {insights.map((item) => (
                <View key={item.id} style={styles.card}>
                  <Text style={styles.cardTitle}>{item.title}</Text>
                  <Text style={styles.cardBody}>
                    {item.insight.explanation}
                  </Text>
                  <Text style={styles.help}>
                    {item.state} · expires{" "}
                    {new Date(item.insight.expires_at).toLocaleDateString()} ·{" "}
                    {item.insight.evidence_refs.length} evidence revisions ·{" "}
                    {item.insight.method_version}
                  </Text>
                  <Text style={styles.help}>{item.insight.uncertainty}</Text>
                  {item.insight.evidence_refs
                    .slice(0, expandedEvidence[item.id] ? undefined : 8)
                    .map((reference) => (
                      <Pressable
                        key={`${reference.object_id}:${reference.revision}`}
                        accessibilityRole="button"
                        onPress={() => openEvidence(reference)}
                        style={styles.evidenceLink}
                      >
                        <Text style={styles.evidenceText}>
                          {reference.object_type} · revision{" "}
                          {reference.revision} · {reference.object_id}
                        </Text>
                      </Pressable>
                    ))}
                  {item.insight.evidence_refs.length > 8 ? (
                    <ActionButton
                      label={
                        expandedEvidence[item.id]
                          ? "Show fewer evidence references"
                          : `Show all ${item.insight.evidence_refs.length} evidence references`
                      }
                      secondary
                      onPress={() => toggleEvidence(item.id)}
                    />
                  ) : null}
                  {item.state === "current" ? (
                    <ActionButton
                      label="Dismiss insight"
                      secondary
                      busy={busy}
                      onPress={() => void changeInsight(item)}
                    />
                  ) : null}
                </View>
              ))}
              {insightCursor ? (
                <ActionButton
                  label="Load more insight history"
                  secondary
                  busy={busy}
                  onPress={() => void loadMoreInsights()}
                />
              ) : null}
            </View>

            <View style={styles.section}>
              <Text accessibilityRole="header" style={styles.sectionTitle}>
                Low-risk tracking suggestions
              </Text>
              {recommendations.length === 0 ? (
                <Text style={styles.help}>
                  No current tracking suggestions.
                </Text>
              ) : null}
              {recommendations.map((item) => (
                <View key={item.id} style={styles.card}>
                  <Text style={styles.cardTitle}>{item.title}</Text>
                  <Text style={styles.cardBody}>
                    {item.recommendation.suggestion}
                  </Text>
                  <Text style={styles.help}>
                    {item.recommendation.rationale} · expires{" "}
                    {new Date(
                      item.recommendation.expires_at,
                    ).toLocaleDateString()}
                  </Text>
                  <Text style={styles.help}>
                    {item.recommendation.expected_review_context}
                  </Text>
                  {item.state === "proposed" ? (
                    <View style={styles.row}>
                      <ActionButton
                        label="Mark as useful"
                        secondary
                        busy={busy}
                        onPress={() =>
                          void changeRecommendation(item, "accepted")
                        }
                      />
                      <ActionButton
                        label="Dismiss"
                        secondary
                        busy={busy}
                        onPress={() =>
                          void changeRecommendation(item, "dismissed")
                        }
                      />
                    </View>
                  ) : (
                    <Text style={styles.help}>
                      State: {item.state}. Accepting records interest only; it
                      does not change health data.
                    </Text>
                  )}
                </View>
              ))}
              {recommendationCursor ? (
                <ActionButton
                  label="Load more recommendation history"
                  secondary
                  busy={busy}
                  onPress={() => void loadMoreRecommendations()}
                />
              ) : null}
            </View>

            <View style={styles.section}>
              <Text accessibilityRole="header" style={styles.sectionTitle}>
                {designLocked
                  ? "Edit experiment notes"
                  : editing
                    ? "Edit experiment draft"
                    : "Manual experiment"}
              </Text>
              <Text style={styles.help}>
                You set the hypothesis, intervention and outcome. The comparison
                is descriptive and does not establish causation.
              </Text>
              <ValueField
                label="Hypothesis"
                value={form.hypothesis}
                onChange={(value) =>
                  setForm((current) => ({ ...current, hypothesis: value }))
                }
                multiline
                disabled={designLocked}
              />
              <ValueField
                label="What you plan to try"
                value={form.intervention}
                onChange={(value) =>
                  setForm((current) => ({ ...current, intervention: value }))
                }
                multiline
                disabled={designLocked}
              />
              <Text style={styles.fieldLabel}>
                Outcome metric: {selectedOutcomeMetric?.label ?? "choose below"}{" "}
                ({selectedOutcomeMetric?.unit ?? ""})
              </Text>
              <View style={styles.choices}>
                {metrics.map((item) => (
                  <SelectButton
                    key={`outcome:${item.metric}`}
                    label={`${item.label} · ${item.unit}`}
                    selected={form.outcome_metric === item.metric}
                    disabled={designLocked}
                    onPress={() =>
                      setForm((current) => ({
                        ...current,
                        outcome_metric: item.metric,
                      }))
                    }
                  />
                ))}
              </View>
              <View style={styles.row}>
                <ValueField
                  label="Baseline starts"
                  value={form.baseline_start}
                  onChange={(value) =>
                    setForm((current) => ({
                      ...current,
                      baseline_start: value,
                    }))
                  }
                  placeholder="YYYY-MM-DD"
                  disabled={designLocked}
                />
                <ValueField
                  label="Intervention starts"
                  value={form.start_date}
                  onChange={(value) =>
                    setForm((current) => ({ ...current, start_date: value }))
                  }
                  placeholder="YYYY-MM-DD"
                  disabled={designLocked}
                />
                <ValueField
                  label="Intervention ends"
                  value={form.end_date}
                  onChange={(value) =>
                    setForm((current) => ({ ...current, end_date: value }))
                  }
                  placeholder="YYYY-MM-DD"
                  disabled={designLocked}
                />
              </View>
              <ValueField
                label="Notes"
                value={form.notes ?? ""}
                onChange={(value) =>
                  setForm((current) => ({ ...current, notes: value }))
                }
                multiline
              />
              {pendingCreate ? (
                <View style={styles.row}>
                  <Text style={styles.help}>
                    The last create response was uncertain. Retry sends the same
                    ID and content; discard it before saving edited fields.
                  </Text>
                  <ActionButton
                    label="Discard uncertain save"
                    secondary
                    onPress={() => setPendingCreate(null)}
                  />
                </View>
              ) : null}
              <View style={styles.row}>
                <ActionButton
                  label={
                    editing
                      ? designLocked
                        ? "Save notes"
                        : "Save draft"
                      : pendingCreate
                        ? "Retry original save"
                        : "Save experiment draft"
                  }
                  busy={busy}
                  disabled={
                    designLocked
                      ? false
                      : !form.hypothesis.trim() || !form.intervention.trim()
                  }
                  onPress={() => void saveExperiment()}
                />
                {editing ? (
                  <ActionButton
                    label="Cancel edit"
                    secondary
                    onPress={() => {
                      setEditing(null);
                      setForm(newExperimentDraft(metric));
                    }}
                  />
                ) : null}
              </View>
              {experiments.map((item) => (
                <View key={item.id} style={styles.card}>
                  <Text style={styles.cardTitle}>{item.title}</Text>
                  <Text style={styles.help}>
                    {item.state} · {item.experiment.baseline_start} to{" "}
                    {item.experiment.end_date} ·{" "}
                    {item.experiment.outcome_metric}
                    {item.experiment.actual_end_at
                      ? ` · ended ${new Date(item.experiment.actual_end_at).toLocaleString()}`
                      : ""}
                  </Text>
                  <Text style={styles.cardBody}>
                    {item.experiment.hypothesis}
                  </Text>
                  {item.state === "draft" && !pendingCreate ? (
                    <ActionButton
                      label="Edit draft"
                      secondary
                      onPress={() => editExperiment(item)}
                    />
                  ) : null}
                  {(["active", "completed", "stopped"] as const).includes(
                    item.state as "active" | "completed" | "stopped",
                  ) ? (
                    <ActionButton
                      label="Edit notes"
                      secondary
                      onPress={() => editExperiment(item)}
                    />
                  ) : null}
                  <View style={styles.row}>
                    {item.state === "draft" ? (
                      <ActionButton
                        label="Start manually"
                        secondary
                        busy={busy}
                        onPress={() =>
                          void transitionExperiment(item, "active")
                        }
                      />
                    ) : null}
                    {item.state === "active" ? (
                      <>
                        <ActionButton
                          label="Complete"
                          secondary
                          busy={busy}
                          onPress={() =>
                            void transitionExperiment(item, "completed")
                          }
                        />
                        <ActionButton
                          label="Stop"
                          secondary
                          busy={busy}
                          onPress={() =>
                            void transitionExperiment(item, "stopped")
                          }
                        />
                      </>
                    ) : null}
                    {item.state === "completed" || item.state === "stopped" ? (
                      <ActionButton
                        label="Archive"
                        secondary
                        busy={busy}
                        onPress={() =>
                          void transitionExperiment(item, "archived")
                        }
                      />
                    ) : null}
                    {(["active", "completed", "stopped"] as const).includes(
                      item.state as "active" | "completed" | "stopped",
                    ) ? (
                      <ActionButton
                        label="View descriptive results"
                        secondary
                        busy={busy}
                        onPress={() => void loadExperimentResult(item)}
                      />
                    ) : null}
                  </View>
                  {results[item.id] ? (
                    <View style={styles.result}>
                      <Text style={styles.help}>
                        Calendar timezone: {results[item.id].timezone}
                      </Text>
                      <Text style={styles.help}>
                        Planned through {item.experiment.end_date}; observed
                        through {results[item.id].intervention.to_date}.
                      </Text>
                      <Text style={styles.cardBody}>
                        Baseline ({results[item.id].baseline.known_days} known,{" "}
                        {results[item.id].baseline.missing_days} missing):{" "}
                        {fmt(
                          results[item.id].baseline.mean,
                          results[item.id].unit,
                        )}
                      </Text>
                      <Text style={styles.cardBody}>
                        Intervention ({results[item.id].intervention.known_days}{" "}
                        known, {results[item.id].intervention.missing_days}{" "}
                        missing):{" "}
                        {fmt(
                          results[item.id].intervention.mean,
                          results[item.id].unit,
                        )}
                      </Text>
                      <Text style={styles.help}>
                        Difference:{" "}
                        {fmt(
                          results[item.id].mean_difference,
                          results[item.id].unit,
                        )}{" "}
                        · {results[item.id].limitation}
                      </Text>
                    </View>
                  ) : null}
                </View>
              ))}
              {experimentCursor ? (
                <ActionButton
                  label="Load more experiment history"
                  secondary
                  busy={busy}
                  onPress={() => void loadMoreExperiments()}
                />
              ) : null}
            </View>
          </>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: "#f7f9f7" },
  content: { gap: 16, padding: 20, paddingBottom: 48 },
  header: { gap: 8, paddingVertical: 8 },
  title: { color: "#17201c", fontSize: 30, fontWeight: "700" },
  body: { color: "#46534d", fontSize: 16, lineHeight: 23 },
  section: {
    backgroundColor: "#edf3ef",
    borderRadius: 16,
    gap: 12,
    padding: 16,
  },
  sectionTitle: { color: "#17201c", fontSize: 21, fontWeight: "700" },
  help: { color: "#596860", fontSize: 14, lineHeight: 20 },
  summary: { color: "#17201c", fontSize: 17, fontWeight: "700" },
  choices: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  choice: {
    backgroundColor: "#fff",
    borderColor: "#aab8af",
    borderRadius: 10,
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 9,
  },
  choiceSelected: { backgroundColor: "#245d3a", borderColor: "#245d3a" },
  choiceText: { color: "#24342b", fontSize: 14 },
  choiceTextSelected: { color: "#fff", fontWeight: "700" },
  field: { flex: 1, gap: 5, minWidth: 120 },
  fieldLabel: { color: "#34463b", fontSize: 14, fontWeight: "600" },
  input: {
    backgroundColor: "#fff",
    borderColor: "#aab8af",
    borderRadius: 10,
    borderWidth: 1,
    color: "#17201c",
    fontSize: 16,
    minHeight: 48,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  multiline: { minHeight: 88, textAlignVertical: "top" },
  row: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  tableHeading: {
    color: "#34463b",
    fontSize: 15,
    fontWeight: "700",
    marginTop: 6,
  },
  tableRow: {
    borderTopColor: "#d4dfd8",
    borderTopWidth: 1,
    gap: 2,
    paddingVertical: 8,
  },
  tableDate: { color: "#17201c", fontSize: 15, fontWeight: "600" },
  tableValue: { color: "#24342b", fontSize: 16 },
  tableMeta: { color: "#596860", fontSize: 13 },
  card: {
    backgroundColor: "#fff",
    borderColor: "#c8d2cb",
    borderRadius: 14,
    borderWidth: 1,
    gap: 8,
    padding: 14,
  },
  cardTitle: { color: "#17201c", fontSize: 17, fontWeight: "700" },
  cardBody: { color: "#34463b", fontSize: 15, lineHeight: 21 },
  result: {
    borderTopColor: "#d4dfd8",
    borderTopWidth: 1,
    gap: 6,
    paddingTop: 8,
  },
  evidenceLink: {
    alignSelf: "flex-start",
    justifyContent: "center",
    minHeight: 36,
  },
  evidenceText: {
    color: "#245d3a",
    fontSize: 13,
    textDecorationLine: "underline",
  },
});
