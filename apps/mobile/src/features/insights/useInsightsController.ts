import { useCallback, useLayoutEffect, useRef, useState } from "react";
import { useFocusEffect } from "expo-router";
import { ApiError } from "@personal-health/api-client";
import type { components } from "@personal-health/api-client";

import { sessionStore } from "../../auth/sessionStore";
import { localCalendarDate, newDailyId, DEVICE_TIMEZONE } from "../daily/model";
import { insightsApi, insightsErrorMessage } from "./api";
import { isCurrentInsightsRequest } from "./state";

type Metric = components["schemas"]["MetricDefinition"];
type Pair = components["schemas"]["AssociationPair"];
type Trend = components["schemas"]["StoredTrendResponse"];
type Association = components["schemas"]["StoredAssociationResponse"];
type Insight = components["schemas"]["InsightResponse"];
type Recommendation = components["schemas"]["RecommendationResponse"];
type Experiment = components["schemas"]["ExperimentResponse"];
type ExperimentDraft = components["schemas"]["ExperimentPayloadV1"];
type ExperimentResult = components["schemas"]["ExperimentResult"];
type PendingExperimentCreate = { id: string; experiment: ExperimentDraft };

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

export function useInsightsController() {
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
  const queryKey = JSON.stringify([metric, selectedPairs, from, to, timezone]);
  const currentQueryKeyRef = useRef(queryKey);
  useLayoutEffect(() => {
    currentQueryKeyRef.current = queryKey;
  }, [queryKey]);
  const queryRequestGeneration = useRef(0);

  function requestIsCurrent(
    generation: number,
    epoch: number,
    requestQueryKey: string,
    requestGeneration: number,
  ): boolean {
    return isCurrentInsightsRequest(
      {
        screenGeneration: screenGeneration.current,
        requestGeneration: queryRequestGeneration.current,
        sessionEpoch: sessionStore.getSnapshot().epoch,
        queryKey: currentQueryKeyRef.current,
      },
      {
        screenGeneration: generation,
        requestGeneration,
        sessionEpoch: epoch,
        queryKey: requestQueryKey,
      },
    );
  }

  function requestOwnsBusyState(
    generation: number,
    epoch: number,
    requestGeneration: number,
  ) {
    return (
      screenGeneration.current === generation &&
      sessionStore.getSnapshot().epoch === epoch &&
      queryRequestGeneration.current === requestGeneration
    );
  }

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
        screenGeneration.current += 1;
      };
    }, []),
  );

  async function runTrend() {
    if (!metric) return;
    const generation = screenGeneration.current;
    const epoch = sessionStore.getSnapshot().epoch;
    const requestQueryKey = currentQueryKeyRef.current;
    const requestGeneration = ++queryRequestGeneration.current;
    setBusy(true);
    setError(null);
    try {
      const result = await insightsApi.getTrend({ metric, from, to, timezone });
      if (
        requestIsCurrent(generation, epoch, requestQueryKey, requestGeneration)
      )
        setTrend(result);
    } catch (requestError) {
      if (
        requestIsCurrent(generation, epoch, requestQueryKey, requestGeneration)
      )
        setError(insightsErrorMessage(requestError));
    } finally {
      if (requestOwnsBusyState(generation, epoch, requestGeneration))
        setBusy(false);
    }
  }

  async function runAssociations() {
    if (!selectedPairs.length) return;
    const generation = screenGeneration.current;
    const epoch = sessionStore.getSnapshot().epoch;
    const requestQueryKey = currentQueryKeyRef.current;
    const requestGeneration = ++queryRequestGeneration.current;
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
        requestIsCurrent(generation, epoch, requestQueryKey, requestGeneration)
      )
        setAssociations(response);
    } catch (requestError) {
      if (
        requestIsCurrent(generation, epoch, requestQueryKey, requestGeneration)
      )
        setError(insightsErrorMessage(requestError));
    } finally {
      if (requestOwnsBusyState(generation, epoch, requestGeneration))
        setBusy(false);
    }
  }

  async function generateInsights() {
    if (!metric && !selectedPairs.length) return;
    const generation = screenGeneration.current;
    const epoch = sessionStore.getSnapshot().epoch;
    const requestQueryKey = currentQueryKeyRef.current;
    const requestGeneration = ++queryRequestGeneration.current;
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
        !requestIsCurrent(generation, epoch, requestQueryKey, requestGeneration)
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
        requestIsCurrent(generation, epoch, requestQueryKey, requestGeneration)
      )
        setError(insightsErrorMessage(requestError));
    } finally {
      if (requestOwnsBusyState(generation, epoch, requestGeneration))
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
    const requestQueryKey = currentQueryKeyRef.current;
    const requestGeneration = ++queryRequestGeneration.current;
    setBusy(true);
    setError(null);
    try {
      const response = await insightsApi.getExperimentResults(
        { experiment_id: item.id },
        { timezone },
      );
      if (
        requestIsCurrent(generation, epoch, requestQueryKey, requestGeneration)
      )
        setResults((current) => ({ ...current, [item.id]: response.result }));
    } catch (requestError) {
      if (
        requestIsCurrent(generation, epoch, requestQueryKey, requestGeneration)
      )
        setError(insightsErrorMessage(requestError));
    } finally {
      if (requestOwnsBusyState(generation, epoch, requestGeneration))
        setBusy(false);
    }
  }

  function cancelExperimentEdit() {
    setEditing(null);
    setForm(newExperimentDraft(metric));
  }

  return {
    metrics,
    pairs,
    insights,
    recommendations,
    experiments,
    insightCursor,
    recommendationCursor,
    experimentCursor,
    expandedEvidence,
    setExpandedEvidence,
    metric,
    setMetric,
    selectedPairs,
    setSelectedPairs,
    from,
    setFrom,
    to,
    setTo,
    timezone,
    setTimezone,
    trend,
    setTrend,
    associations,
    setAssociations,
    results,
    setResults,
    form,
    setForm,
    editing,
    setEditing,
    pendingCreate,
    setPendingCreate,
    loading,
    busy,
    error,
    runTrend,
    runAssociations,
    generateInsights,
    loadMoreInsights,
    loadMoreRecommendations,
    loadMoreExperiments,
    changeInsight,
    changeRecommendation,
    saveExperiment,
    editExperiment,
    cancelExperimentEdit,
    transitionExperiment,
    loadExperimentResult,
  };
}
