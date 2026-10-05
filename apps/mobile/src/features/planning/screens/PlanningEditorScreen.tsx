import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import {
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import type { components } from "@personal-health/api-client";
import { ApiError } from "@personal-health/api-client";

import {
  ActionButton,
  LoadingMessage,
  StatusMessage,
} from "../../profile/components/Ui";
import { newDailyId } from "../../daily/model";
import { sessionStore } from "../../../auth/sessionStore";
import { profileApi } from "../../profile/api";
import {
  activePlanningCreateRecovery,
  type PlanningCreateAttempt,
  type PlanningItem,
  planningApi,
  planningErrorMessage,
  sendPlanningCreate,
} from "../api";
import { nextTrackerFieldId } from "../trackerEntry";
import { canAdvancePlanningRevision } from "../editState";
import { RequestScope } from "../../profile/requestScope";

type Kind = "goal" | "regimen" | "plan" | "context" | "tracker_definition";
type TrackerField = components["schemas"]["TrackerFieldV1"];
type ContextRelation = components["schemas"]["ContextRelation"];
type ContextTarget = { id: string; title: string; kind: string };
const DOMAINS = [
  "general",
  "nutrition",
  "exercise",
  "sleep",
  "symptoms",
  "measurements",
] as const;
const TRACKER_DOMAINS = [
  "nutrition",
  "exercise",
  "sleep",
  "symptoms",
  "measurements",
] as const;
const FIELD_KINDS = [
  "text",
  "number",
  "boolean",
  "enum",
  "date",
  "quantity",
] as const;
const TRACKER_UNITS = [
  "kg",
  "g",
  "lb",
  "mg",
  "mcg",
  "ml",
  "l",
  "cm",
  "m",
  "in",
  "mmHg",
  "bpm",
  "%",
  "day",
  "week",
  "year",
  "dose",
] as const;
const GOAL_METRICS_BY_DOMAIN: Record<string, readonly string[]> = {
  general: [],
  nutrition: ["energy"],
  exercise: ["duration", "distance"],
  sleep: ["duration"],
  symptoms: ["symptom_severity", "symptom_episode_count"],
  measurements: [
    "weight",
    "temperature",
    "systolic_pressure",
    "diastolic_pressure",
    "pulse",
  ],
};
const GOAL_UNITS: Record<string, readonly string[]> = {
  energy: ["kcal", "kJ"],
  duration: ["min", "h"],
  distance: ["m", "km", "mi"],
  weight: ["kg", "lb"],
  temperature: ["C", "F"],
  systolic_pressure: ["mmHg"],
  diastolic_pressure: ["mmHg"],
  pulse: ["bpm"],
  symptom_severity: ["score"],
  symptom_episode_count: ["episodes"],
};

export default function PlanningEditorScreen() {
  const params = useLocalSearchParams<{ kind?: string; id?: string }>();
  const router = useRouter();
  const kind = (params.kind ?? "goal") as Kind;
  const editing = Boolean(params.id);
  const [original, setOriginal] = useState<PlanningItem | null>(null);
  const [label, setLabel] = useState("");
  const [domain, setDomain] = useState<string>(
    kind === "tracker_definition" ? "measurements" : "general",
  );
  const [category, setCategory] = useState<string>(
    kind === "regimen" ? "habit" : kind === "context" ? "other" : "",
  );
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [targetDate, setTargetDate] = useState("");
  const [targetMetric, setTargetMetric] = useState("none");
  const [targetComparator, setTargetComparator] = useState("at_least");
  const [targetValue, setTargetValue] = useState("");
  const [targetUnit, setTargetUnit] = useState("kcal");
  const [targetPeriod, setTargetPeriod] = useState("once");
  const [regimenQuantity, setRegimenQuantity] = useState("");
  const [regimenUnit, setRegimenUnit] = useState("dose");
  const [regimenInstructions, setRegimenInstructions] = useState("");
  const [contextNotes, setContextNotes] = useState("");
  const [contextPriority, setContextPriority] = useState("0");
  const [contextTargets, setContextTargets] = useState<ContextTarget[]>([]);
  const [contextRelated, setContextRelated] = useState<ContextRelation[]>([]);
  const [pickerCursors, setPickerCursors] = useState<
    Record<string, string | null>
  >({});
  const [loadingPicker, setLoadingPicker] = useState<string | null>(null);
  const [fields, setFields] = useState<TrackerField[]>([
    { id: "value", label: "Value", kind: "text", required: false, choices: [] },
  ]);
  const [planItems, setPlanItems] = useState<
    components["schemas"]["PlanItemInput"][]
  >([]);
  const [availableReferences, setAvailableReferences] = useState<
    PlanningItem[]
  >([]);
  const [planItemKind, setPlanItemKind] = useState<"task" | "goal" | "regimen">(
    "task",
  );
  const [planItemLabel, setPlanItemLabel] = useState("");
  const [planItemReference, setPlanItemReference] = useState<string | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(editing);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const [conflictReloadRequired, setConflictReloadRequired] = useState(false);
  const firstFocus = useRef(true);
  const [recoveryAttempt, setRecoveryAttempt] =
    useState<PlanningCreateAttempt | null>(() =>
      activePlanningCreateRecovery.retryOriginal(),
    );
  const [aiUseAllowed, setAiUseAllowed] = useState(false);
  const [crossDomainUseAllowed, setCrossDomainUseAllowed] = useState(false);
  const originalRef = useRef<PlanningItem | null>(null);
  const replaceDraftOnReload = useRef(false);
  const pickerScope = useRef(new RequestScope());
  const pickerReadyGeneration = useRef<number | null>(null);
  const pickerScopeKey = `pickers:${kind}:${reloadToken}`;

  useEffect(() => {
    const scope = pickerScope.current;
    const pickerToken = scope.start(pickerScopeKey);
    pickerReadyGeneration.current = null;
    const pickerIsCurrent = () => scope.isCurrent(pickerToken);
    if (kind === "plan") {
      Promise.all([
        planningApi.listGoals({ limit: 100 }),
        planningApi.listRegimens({ limit: 100 }),
      ])
        .then(([goals, regimens]) => {
          if (!pickerIsCurrent()) return;
          setAvailableReferences([...goals.items, ...regimens.items]);
          pickerReadyGeneration.current = pickerToken.generation;
          setPickerCursors((current) => ({
            ...current,
            goal: goals.next_cursor,
            regimen: regimens.next_cursor,
          }));
        })
        .catch((error: unknown) => {
          if (pickerIsCurrent()) setError(planningErrorMessage(error));
        })
        .finally(() => {
          if (pickerIsCurrent()) setLoadingPicker(null);
        });
    }
    if (kind === "context") {
      Promise.all([
        planningApi.listGoals({ limit: 100 }),
        planningApi.listRegimens({ limit: 100 }),
        profileApi.listProfileItems({ limit: 100 }),
      ])
        .then(([goals, regimens, profiles]) => {
          if (!pickerIsCurrent()) return;
          pickerReadyGeneration.current = pickerToken.generation;
          setContextTargets([
            ...goals.items.map((item) => ({
              id: item.id,
              title: item.title,
              kind: "goal",
            })),
            ...regimens.items.map((item) => ({
              id: item.id,
              title: item.title,
              kind: "regimen",
            })),
            ...profiles.items.map((item) => ({
              id: item.id,
              title: item.title,
              kind: "Profile",
            })),
          ]);
          setPickerCursors((current) => ({
            ...current,
            goal: goals.next_cursor,
            regimen: regimens.next_cursor,
            profile: profiles.next_cursor,
          }));
        })
        .catch((error: unknown) => {
          if (pickerIsCurrent()) setError(planningErrorMessage(error));
        })
        .finally(() => {
          if (pickerIsCurrent()) setLoadingPicker(null);
        });
    }
    if (!editing || !params.id) return () => scope.invalidate(pickerToken);
    let current = true;
    if (!originalRef.current || replaceDraftOnReload.current) setLoading(true);
    const request = async () => {
      if (kind === "goal") return planningApi.getGoal({ goal_id: params.id! });
      if (kind === "regimen")
        return planningApi.getRegimen({ regimen_id: params.id! });
      if (kind === "plan") return planningApi.getPlan({ plan_id: params.id! });
      if (kind === "context")
        return planningApi.getContext({ context_id: params.id! });
      return planningApi.getTracker({ tracker_id: params.id! });
    };
    request()
      .then((item) => {
        if (!current) return;
        if (
          originalRef.current?.id === item.id &&
          !replaceDraftOnReload.current
        ) {
          if (!canAdvancePlanningRevision(originalRef.current, item)) {
            setConflictReloadRequired(true);
            setError(
              "Server content changed. Your draft is retained. Reload the latest item before replacing its content.",
            );
            return;
          }
          originalRef.current = item;
          setOriginal(item);
          setError(null);
          return;
        }
        replaceDraftOnReload.current = false;
        setConflictReloadRequired(false);
        originalRef.current = item;
        setOriginal(item);
        setAiUseAllowed(item.ai_use_allowed);
        setCrossDomainUseAllowed(item.cross_domain_use_allowed);
        if (item.object_type === "goal") {
          setLabel(item.goal.label);
          setDomain(item.goal.domain);
          setStartDate(item.goal.start_date ?? "");
          setTargetDate(item.goal.target_date ?? "");
          if (item.goal.target) {
            setTargetMetric(item.goal.target.metric);
            setTargetComparator(item.goal.target.comparator);
            setTargetValue(String(item.goal.target.value));
            setTargetUnit(item.goal.target.unit);
            setTargetPeriod(item.goal.target_period ?? "once");
          } else {
            setTargetMetric("none");
            setTargetValue("");
            setTargetPeriod("once");
          }
        } else if (item.object_type === "regimen") {
          setLabel(item.regimen.label);
          setDomain(item.regimen.domain ?? "general");
          setCategory(item.regimen.kind);
          setStartDate(item.regimen.start_date ?? "");
          setEndDate(item.regimen.end_date ?? "");
          setRegimenQuantity(
            item.regimen.quantity ? String(item.regimen.quantity.value) : "",
          );
          setRegimenUnit(item.regimen.quantity?.unit ?? "dose");
          setRegimenInstructions(item.regimen.instructions ?? "");
        } else if (item.object_type === "plan") {
          setLabel(item.plan.label);
          setPlanItems(item.plan.items ?? []);
          setStartDate(item.plan.start_date ?? "");
          setEndDate(item.plan.end_date ?? "");
        } else if (item.object_type === "context") {
          setLabel(item.context.label);
          setCategory(item.context.context_type);
          setStartDate(item.context.start_at ?? "");
          setEndDate(item.context.end_at ?? "");
          setContextNotes(item.context.notes ?? "");
          setContextPriority(String(item.context.priority ?? 0));
          setContextRelated(item.context.related ?? []);
        } else {
          setLabel(item.definition.name);
          setDomain(item.definition.domain);
          setFields(item.definition.fields);
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
      scope.invalidate(pickerToken);
    };
  }, [editing, kind, params.id, reloadToken, pickerScopeKey]);

  async function loadMorePicker(targetKind: "goal" | "regimen" | "profile") {
    const cursor = pickerCursors[targetKind];
    const token = pickerScope.current.tokenFor(pickerScopeKey);
    if (!cursor || loadingPicker || !token) return;
    if (pickerReadyGeneration.current !== token.generation) return;
    if (!pickerScope.current.beginPage(token, `${targetKind}:${cursor}`))
      return;
    setLoadingPicker(targetKind);
    setError(null);
    try {
      if (targetKind === "profile") {
        const page = await profileApi.listProfileItems({ limit: 100, cursor });
        if (!pickerScope.current.isCurrent(token)) return;
        setContextTargets((current) => [
          ...current,
          ...page.items.map((item) => ({
            id: item.id,
            title: item.title,
            kind: "Profile",
          })),
        ]);
        setPickerCursors((current) => ({
          ...current,
          profile: page.next_cursor,
        }));
      } else {
        const page =
          targetKind === "goal"
            ? await planningApi.listGoals({ limit: 100, cursor })
            : await planningApi.listRegimens({ limit: 100, cursor });
        if (!pickerScope.current.isCurrent(token)) return;
        setPickerCursors((current) => ({
          ...current,
          [targetKind]: page.next_cursor,
        }));
        if (kind === "plan")
          setAvailableReferences((current) => [...current, ...page.items]);
        else
          setContextTargets((current) => [
            ...current,
            ...page.items.map((item) => ({
              id: item.id,
              title: item.title,
              kind: item.object_type,
            })),
          ]);
      }
    } catch (requestError) {
      if (pickerScope.current.isCurrent(token))
        setError(planningErrorMessage(requestError));
    } finally {
      pickerScope.current.finishPage(token, `${targetKind}:${cursor}`);
      if (pickerScope.current.isCurrent(token)) setLoadingPicker(null);
    }
  }

  useFocusEffect(
    useCallback(() => {
      if (firstFocus.current) {
        firstFocus.current = false;
        return;
      }
      setReloadToken((value) => value + 1);
    }, []),
  );

  async function sendCreate(attempt: PlanningCreateAttempt): Promise<boolean> {
    const isCurrent = () => {
      const latest = sessionStore.getSnapshot();
      return (
        latest.epoch === attempt.sessionEpoch &&
        latest.userId === attempt.sessionUserId
      );
    };
    if (!isCurrent()) return false;
    const prepared = activePlanningCreateRecovery.prepare(attempt);
    try {
      await sendPlanningCreate(prepared);
      if (!isCurrent()) return false;
      activePlanningCreateRecovery.resolve();
      setRecoveryAttempt(null);
      return true;
    } catch (requestError) {
      if (!isCurrent()) return false;
      const uncertain = activePlanningCreateRecovery.markFailure(
        prepared,
        requestError,
      );
      setRecoveryAttempt(uncertain ? prepared : null);
      if (uncertain) {
        throw new Error(
          "The save result is uncertain. Retry the original request before changing details.",
        );
      }
      throw requestError;
    }
  }

  async function retryOriginalCreate() {
    if (!recoveryAttempt) return;
    const latest = sessionStore.getSnapshot();
    if (
      latest.epoch !== recoveryAttempt.sessionEpoch ||
      latest.userId !== recoveryAttempt.sessionUserId
    )
      return;
    setBusy(true);
    setError(null);
    try {
      if (await sendCreate(recoveryAttempt)) router.replace("/planning");
    } catch (requestError) {
      if (requestError instanceof ApiError)
        setError(planningErrorMessage(requestError));
      else
        setError(
          requestError instanceof Error
            ? requestError.message
            : planningErrorMessage(requestError),
        );
    } finally {
      const current = sessionStore.getSnapshot();
      if (
        current.epoch === recoveryAttempt.sessionEpoch &&
        current.userId === recoveryAttempt.sessionUserId
      ) {
        setBusy(false);
      }
    }
  }

  const title = useMemo(
    () => `${editing ? "Edit" : "Create"} ${kindLabel(kind)}`,
    [editing, kind],
  );

  async function submit() {
    const sessionAtSubmit = sessionStore.getSnapshot();
    const isCurrentSession = () => {
      const latest = sessionStore.getSnapshot();
      return (
        latest.epoch === sessionAtSubmit.epoch &&
        latest.userId === sessionAtSubmit.userId
      );
    };
    setError(null);
    if (editing && conflictReloadRequired) {
      setError("Reload the latest planning item before saving this draft.");
      return;
    }
    if (editing && !original) {
      setError("Load the planning item before saving changes.");
      return;
    }
    if (!label.trim()) {
      setError("Enter a name before saving.");
      return;
    }
    const dates =
      kind === "goal"
        ? [startDate, targetDate]
        : kind === "regimen" || kind === "plan" || kind === "context"
          ? [startDate, endDate]
          : [];
    if (dates.some((value) => value && !isCalendarDate(value))) {
      setError("Dates must be real calendar dates in YYYY-MM-DD format.");
      return;
    }
    if (startDate && endDate && endDate < startDate) {
      setError("The end date must be on or after the start date.");
      return;
    }
    if (startDate && targetDate && targetDate < startDate) {
      setError("The target date must be on or after the start date.");
      return;
    }
    setBusy(true);
    try {
      const id = original?.id ?? newDailyId();
      const revision = original?.revision ?? 0;
      const session = sessionStore.getSnapshot();
      if (kind === "goal") {
        let target: components["schemas"]["MetricTarget"] | null = null;
        if (targetMetric !== "none") {
          const numericTarget = Number(targetValue);
          if (
            !targetValue.trim() ||
            !Number.isFinite(numericTarget) ||
            numericTarget < 0
          ) {
            setError("Enter a nonnegative finite value for the goal target.");
            return;
          }
          if (!(GOAL_METRICS_BY_DOMAIN[domain] ?? []).includes(targetMetric)) {
            setError(
              "Choose a target metric that belongs to this goal domain.",
            );
            return;
          }
          target = {
            metric: targetMetric as components["schemas"]["MetricKey"],
            comparator:
              targetComparator as components["schemas"]["GoalComparator"],
            value: numericTarget,
            unit: targetUnit as components["schemas"]["MeasurementUnit"],
          };
        }
        const goal: components["schemas"]["GoalPayloadV1"] = {
          ...(original?.object_type === "goal" ? original.goal : {}),
          label: label.trim(),
          domain: domain as components["schemas"]["GoalDomain"],
          start_date: startDate || null,
          target_date: targetDate || null,
          target,
          target_period: target
            ? (targetPeriod as components["schemas"]["GoalPayloadV1"]["target_period"])
            : null,
        };
        if (editing)
          await planningApi.updateGoal(
            { goal_id: id },
            {
              expected_revision: revision,
              goal,
              ai_use_allowed: aiUseAllowed,
              cross_domain_use_allowed: crossDomainUseAllowed,
            },
          );
        else if (
          !(await sendCreate({
            kind: "goal",
            body: {
              id,
              goal,
              ai_use_allowed: aiUseAllowed,
              cross_domain_use_allowed: crossDomainUseAllowed,
            },
            sessionEpoch: session.epoch,
            sessionUserId: session.userId,
          }))
        )
          return;
      } else if (kind === "regimen") {
        const quantityValue = regimenQuantity.trim()
          ? Number(regimenQuantity)
          : null;
        if (
          quantityValue !== null &&
          (!Number.isFinite(quantityValue) || quantityValue < 0)
        ) {
          setError("Enter a nonnegative finite regimen quantity.");
          return;
        }
        if (regimenInstructions.length > 2000) {
          setError("Instructions can be at most 2,000 characters.");
          return;
        }
        const regimen: components["schemas"]["RegimenPayloadV1"] = {
          ...(original?.object_type === "regimen" ? original.regimen : {}),
          label: label.trim(),
          kind: category as components["schemas"]["RegimenKind"],
          domain: domain as components["schemas"]["GoalDomain"],
          start_date: startDate || null,
          end_date: endDate || null,
          instructions: regimenInstructions.trim() || null,
          quantity:
            quantityValue === null
              ? null
              : {
                  value: quantityValue,
                  unit: regimenUnit as components["schemas"]["ProfileUnit"],
                },
        };
        if (editing)
          await planningApi.updateRegimen(
            { regimen_id: id },
            {
              expected_revision: revision,
              regimen,
              ai_use_allowed: aiUseAllowed,
              cross_domain_use_allowed: crossDomainUseAllowed,
            },
          );
        else if (
          !(await sendCreate({
            kind: "regimen",
            body: {
              id,
              regimen,
              ai_use_allowed: aiUseAllowed,
              cross_domain_use_allowed: crossDomainUseAllowed,
            },
            sessionEpoch: session.epoch,
            sessionUserId: session.userId,
          }))
        )
          return;
      } else if (kind === "plan") {
        const plan: components["schemas"]["PlanPayloadV1"] = {
          ...(original?.object_type === "plan" ? original.plan : {}),
          label: label.trim(),
          items: planItems,
          start_date: startDate || null,
          end_date: endDate || null,
        };
        if (editing)
          await planningApi.updatePlan(
            { plan_id: id },
            {
              expected_revision: revision,
              plan,
              ai_use_allowed: aiUseAllowed,
              cross_domain_use_allowed: crossDomainUseAllowed,
            },
          );
        else if (
          !(await sendCreate({
            kind: "plan",
            body: {
              id,
              plan,
              ai_use_allowed: aiUseAllowed,
              cross_domain_use_allowed: crossDomainUseAllowed,
            },
            sessionEpoch: session.epoch,
            sessionUserId: session.userId,
          }))
        )
          return;
      } else if (kind === "context") {
        const priority = Number(contextPriority);
        if (!Number.isInteger(priority) || priority < 0 || priority > 100) {
          setError(
            "Context priority must be a whole number from 0 through 100.",
          );
          return;
        }
        if (contextNotes.length > 2000 || contextRelated.length > 20) {
          setError("Context notes or linked items exceed the allowed limit.");
          return;
        }
        const context: components["schemas"]["ContextPayloadV1"] = {
          ...(original?.object_type === "context" ? original.context : {}),
          label: label.trim(),
          context_type: category as components["schemas"]["ContextType"],
          priority,
          notes: contextNotes.trim() || null,
          start_at: startDate || null,
          end_at: endDate || null,
          related: contextRelated,
        };
        if (editing)
          await planningApi.updateContext(
            { context_id: id },
            {
              expected_revision: revision,
              context,
              ai_use_allowed: aiUseAllowed,
              cross_domain_use_allowed: crossDomainUseAllowed,
            },
          );
        else if (
          !(await sendCreate({
            kind: "context",
            body: {
              id,
              context,
              ai_use_allowed: aiUseAllowed,
              cross_domain_use_allowed: crossDomainUseAllowed,
            },
            sessionEpoch: session.epoch,
            sessionUserId: session.userId,
          }))
        )
          return;
      } else {
        if (
          fields.length === 0 ||
          fields.some((field) => !field.id.trim() || !field.label.trim())
        ) {
          setError("Each tracker field needs an ID and label.");
          return;
        }
        const definition: components["schemas"]["TrackerDefinitionV1"] = {
          name: label.trim(),
          domain: domain as components["schemas"]["DailyDomain"],
          fields: fields.map((field) => ({
            ...field,
            id: field.id.trim(),
            label: field.label.trim(),
            choices: field.kind === "enum" ? (field.choices ?? []) : [],
            unit: field.kind === "quantity" ? (field.unit ?? "dose") : null,
          })),
        };
        if (editing)
          await planningApi.updateTracker(
            { tracker_id: id },
            {
              expected_revision: revision,
              definition,
              ai_use_allowed: aiUseAllowed,
              cross_domain_use_allowed: crossDomainUseAllowed,
            },
          );
        else if (
          !(await sendCreate({
            kind: "tracker_definition",
            body: {
              id,
              definition,
              ai_use_allowed: aiUseAllowed,
              cross_domain_use_allowed: crossDomainUseAllowed,
            },
            sessionEpoch: session.epoch,
            sessionUserId: session.userId,
          }))
        )
          return;
      }
      if (!isCurrentSession()) return;
      router.replace("/planning");
    } catch (requestError) {
      if (!isCurrentSession()) return;
      setConflictReloadRequired(
        requestError instanceof ApiError && requestError.status === 409,
      );
      setError(
        requestError instanceof ApiError
          ? planningErrorMessage(requestError)
          : requestError instanceof Error
            ? requestError.message
            : planningErrorMessage(requestError),
      );
    } finally {
      if (isCurrentSession()) setBusy(false);
    }
  }

  if (loading) return <LoadingMessage label="Loading planning item" />;
  if (editing && !original) {
    return (
      <SafeAreaView style={styles.safeArea}>
        <ScrollView contentContainerStyle={styles.content}>
          <Text accessibilityRole="header" style={styles.title}>
            Planning item not loaded
          </Text>
          <StatusMessage
            title="Could not load planning item"
            message={
              error ??
              "The editor needs current server data before it can save."
            }
            tone="error"
          />
          <ActionButton
            label="Retry loading item"
            busy={loading}
            onPress={() => setReloadToken((value) => value + 1)}
          />
          <ActionButton label="Back" secondary onPress={() => router.back()} />
        </ScrollView>
      </SafeAreaView>
    );
  }
  const currentSession = sessionStore.getSnapshot();
  const pendingCreate =
    recoveryAttempt &&
    recoveryAttempt.sessionEpoch === currentSession.epoch &&
    recoveryAttempt.sessionUserId === currentSession.userId
      ? recoveryAttempt
      : null;
  if (pendingCreate) {
    return (
      <SafeAreaView style={styles.safeArea}>
        <ScrollView contentContainerStyle={styles.content}>
          <Text accessibilityRole="header" style={styles.title}>
            Recover planning save
          </Text>
          <Text style={styles.subtitle}>
            The original {kindLabel(pendingCreate.kind).toLowerCase()} save may
            have completed. Retry its retained ID and request before editing or
            creating another item.
          </Text>
          {error ? (
            <StatusMessage
              title="Save recovery failed"
              message={error}
              tone="error"
            />
          ) : null}
          <ActionButton
            label="Retry original save"
            busy={busy}
            onPress={() => void retryOriginalCreate()}
          />
          <ActionButton
            label="Back to Plan"
            secondary
            disabled={busy}
            onPress={() => router.replace("/planning")}
          />
        </ScrollView>
      </SafeAreaView>
    );
  }
  if (original?.status === "archived") {
    return (
      <SafeAreaView style={styles.safeArea}>
        <ScrollView contentContainerStyle={styles.content}>
          <Text accessibilityRole="header" style={styles.title}>
            Archived {kindLabel(original.object_type)}
          </Text>
          <View style={styles.fieldCard}>
            <Text style={styles.cardTitle}>{original.title}</Text>
            <Text style={styles.noteText}>
              Revision {original.revision} · retained in history
            </Text>
            <Text style={styles.noteText}>
              AI use: {original.ai_use_allowed ? "allowed" : "not allowed"} ·
              cross-domain use:{" "}
              {original.cross_domain_use_allowed ? "allowed" : "not allowed"}
            </Text>
            <Text style={styles.body}>{archivedDetails(original)}</Text>
            {original.notes ? (
              <Text style={styles.body}>{original.notes}</Text>
            ) : null}
          </View>
          <StatusMessage
            title="Read-only"
            message="Archived planning items remain available for reference and history. They cannot be edited or scheduled."
          />
          <ActionButton
            label="View revision history"
            secondary
            onPress={() =>
              router.push({
                pathname: "/planning/history",
                params: { kind: original.object_type, id: original.id },
              })
            }
          />
          <ActionButton
            label="Back to Plan"
            onPress={() => router.replace("/planning")}
          />
        </ScrollView>
      </SafeAreaView>
    );
  }
  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text accessibilityRole="header" style={styles.title}>
          {title}
        </Text>
        <Text style={styles.subtitle}>
          Intent stays separate from events and observations you actually
          record.
        </Text>
        {error ? (
          <StatusMessage title="Could not save" message={error} tone="error" />
        ) : null}
        {editing && conflictReloadRequired ? (
          <ActionButton
            label="Reload latest and replace this draft"
            secondary
            onPress={() => {
              setError(null);
              replaceDraftOnReload.current = true;
              setReloadToken((value) => value + 1);
            }}
          />
        ) : null}
        <Input
          label={kind === "tracker_definition" ? "Tracker name" : "Name"}
          value={label}
          onChange={setLabel}
        />

        <View style={styles.fieldCard}>
          <Text accessibilityRole="header" style={styles.sectionTitle}>
            Permissions
          </Text>
          <Text style={styles.noteText}>
            These permissions default off. Turn them on only when you want to
            authorize the stated use.
          </Text>
          <ActionButton
            label={`AI use: ${aiUseAllowed ? "allowed" : "not allowed"}`}
            secondary
            onPress={() => setAiUseAllowed((value) => !value)}
          />
          <ActionButton
            label={`Cross-domain use: ${crossDomainUseAllowed ? "allowed" : "not allowed"}`}
            secondary
            onPress={() => setCrossDomainUseAllowed((value) => !value)}
          />
        </View>

        {kind === "goal" || kind === "regimen" ? (
          <ChoiceField
            label="Domain"
            options={DOMAINS}
            value={domain}
            onChange={(next) => {
              setDomain(next);
              if (!(GOAL_METRICS_BY_DOMAIN[next] ?? []).includes(targetMetric))
                setTargetMetric("none");
            }}
          />
        ) : null}
        {kind === "goal" ? (
          <View style={styles.fieldCard}>
            <Text accessibilityRole="header" style={styles.sectionTitle}>
              Optional target
            </Text>
            <ChoiceField
              label="Metric"
              options={["none", ...(GOAL_METRICS_BY_DOMAIN[domain] ?? [])]}
              value={targetMetric}
              onChange={(metric) => {
                setTargetMetric(metric);
                const units = GOAL_UNITS[metric];
                if (units?.[0]) setTargetUnit(units[0]);
              }}
            />
            {targetMetric !== "none" ? (
              <>
                <ChoiceField
                  label="Comparison"
                  options={["at_least", "at_most", "equal"] as const}
                  value={targetComparator}
                  onChange={setTargetComparator}
                />
                <Input
                  label="Target value"
                  value={targetValue}
                  onChange={setTargetValue}
                  keyboardType="decimal-pad"
                />
                <ChoiceField
                  label="Target unit"
                  options={GOAL_UNITS[targetMetric] ?? []}
                  value={targetUnit}
                  onChange={setTargetUnit}
                />
                <ChoiceField
                  label="Target period"
                  options={["once", "day", "week", "month", "year"] as const}
                  value={targetPeriod}
                  onChange={setTargetPeriod}
                />
              </>
            ) : null}
            <Input
              label="Starts on (YYYY-MM-DD)"
              value={startDate}
              onChange={setStartDate}
            />
            <Input
              label="Target date (YYYY-MM-DD)"
              value={targetDate}
              onChange={setTargetDate}
            />
          </View>
        ) : null}
        {kind === "regimen" ? (
          <View style={styles.fieldCard}>
            <ChoiceField
              label="Regimen type"
              options={
                ["habit", "medication", "supplement", "activity"] as const
              }
              value={category}
              onChange={setCategory}
            />
            <Input
              label="Optional quantity"
              value={regimenQuantity}
              onChange={setRegimenQuantity}
              keyboardType="decimal-pad"
            />
            {regimenQuantity.trim() ? (
              <ChoiceField
                label="Quantity unit"
                options={TRACKER_UNITS}
                value={regimenUnit}
                onChange={setRegimenUnit}
              />
            ) : null}
            <Text style={styles.inputLabel}>Optional instructions</Text>
            <TextInput
              accessibilityLabel="Optional instructions"
              value={regimenInstructions}
              onChangeText={setRegimenInstructions}
              multiline
              maxLength={2000}
              style={[styles.input, styles.multiline]}
            />
            <Input
              label="Starts on (YYYY-MM-DD)"
              value={startDate}
              onChange={setStartDate}
            />
            <Input
              label="Ends on (YYYY-MM-DD)"
              value={endDate}
              onChange={setEndDate}
            />
          </View>
        ) : null}
        {kind === "plan" ? (
          <View style={styles.fieldCard}>
            <Input
              label="Starts on (YYYY-MM-DD)"
              value={startDate}
              onChange={setStartDate}
            />
            <Input
              label="Ends on (YYYY-MM-DD)"
              value={endDate}
              onChange={setEndDate}
            />
          </View>
        ) : null}
        {kind === "context" ? (
          <View style={styles.fieldCard}>
            <ChoiceField
              label="Context type"
              options={
                [
                  "travel",
                  "illness",
                  "recovery",
                  "schedule_change",
                  "other",
                ] as const
              }
              value={category}
              onChange={setCategory}
            />
            <Input
              label="Starts on (YYYY-MM-DD)"
              value={startDate}
              onChange={setStartDate}
            />
            <Input
              label="Ends on (YYYY-MM-DD)"
              value={endDate}
              onChange={setEndDate}
            />
            <Input
              label="Priority (0–100)"
              value={contextPriority}
              onChange={setContextPriority}
              keyboardType="number-pad"
            />
            <Text style={styles.inputLabel}>Notes</Text>
            <TextInput
              accessibilityLabel="Context notes"
              value={contextNotes}
              onChangeText={setContextNotes}
              multiline
              maxLength={2000}
              style={[styles.input, styles.multiline]}
            />
            <Text accessibilityRole="header" style={styles.inputLabel}>
              Related Profile items, goals, and regimens
            </Text>
            {contextTargets.map((target) => {
              const selected = contextRelated.some(
                (relation) => relation.object_id === target.id,
              );
              return (
                <Pressable
                  key={target.id}
                  accessibilityRole="button"
                  accessibilityState={{ selected }}
                  onPress={() =>
                    setContextRelated((current) =>
                      selected
                        ? current.filter(
                            (relation) => relation.object_id !== target.id,
                          )
                        : current.length >= 20
                          ? current
                          : [
                              ...current,
                              {
                                object_id: target.id,
                                priority: 0,
                                relevance: "related",
                              },
                            ],
                    )
                  }
                  style={[
                    styles.targetChoice,
                    selected && styles.targetChoiceSelected,
                  ]}
                >
                  <Text style={styles.choiceText}>
                    {target.kind} · {target.title}
                  </Text>
                  <Text style={styles.noteText}>
                    {selected ? "Linked" : "Tap to link"}
                  </Text>
                </Pressable>
              );
            })}
            {(["goal", "regimen", "profile"] as const).map((targetKind) =>
              pickerCursors[targetKind] ? (
                <ActionButton
                  key={targetKind}
                  label={`Load more ${targetKind === "profile" ? "Profile items" : `${targetKind}s`}`}
                  secondary
                  busy={loadingPicker === targetKind}
                  disabled={
                    loadingPicker !== null && loadingPicker !== targetKind
                  }
                  onPress={() => void loadMorePicker(targetKind)}
                />
              ) : null,
            )}
            {contextTargets.length === 0 ? (
              <Text style={styles.noteText}>
                No Profile items, goals, or regimens are available to link.
              </Text>
            ) : null}
          </View>
        ) : null}
        {kind === "tracker_definition" ? (
          <>
            <ChoiceField
              label="Tracker domain"
              options={TRACKER_DOMAINS}
              value={domain}
              onChange={setDomain}
            />
            <Text accessibilityRole="header" style={styles.sectionTitle}>
              Fields
            </Text>
            {fields.map((field, index) => (
              <View key={`${index}:${field.id}`} style={styles.fieldCard}>
                <Input
                  label="Stable field ID"
                  value={field.id}
                  onChange={(value) => updateField(index, { id: value })}
                />
                <Input
                  label="Field label"
                  value={field.label}
                  onChange={(value) => updateField(index, { label: value })}
                />
                <ChoiceField
                  label="Field type"
                  options={FIELD_KINDS}
                  value={field.kind}
                  onChange={(value) =>
                    updateField(index, {
                      kind: value as TrackerField["kind"],
                      choices: value === "enum" ? field.choices : [],
                      unit:
                        value === "quantity" ? (field.unit ?? "dose") : null,
                    })
                  }
                />
                {field.kind === "enum" ? (
                  <Input
                    label="Choices, separated by commas"
                    value={(field.choices ?? []).join(", ")}
                    onChange={(value) =>
                      updateField(index, {
                        choices: value
                          .split(",")
                          .map((choice) => choice.trim())
                          .filter(Boolean),
                      })
                    }
                  />
                ) : null}
                {field.kind === "quantity" ? (
                  <ChoiceField
                    label="Supported unit"
                    options={TRACKER_UNITS}
                    value={field.unit ?? "dose"}
                    onChange={(value) =>
                      updateField(index, {
                        unit: value as TrackerField["unit"],
                      })
                    }
                  />
                ) : null}
                <ActionButton
                  label={field.required ? "Required: yes" : "Required: no"}
                  secondary
                  onPress={() =>
                    updateField(index, { required: !field.required })
                  }
                />
                {fields.length > 1 ? (
                  <ActionButton
                    label="Remove field"
                    secondary
                    onPress={() =>
                      setFields((current) =>
                        current.filter((_, fieldIndex) => fieldIndex !== index),
                      )
                    }
                  />
                ) : null}
              </View>
            ))}
            <ActionButton
              label="Add field"
              secondary
              disabled={fields.length >= 20}
              onPress={() =>
                setFields((current) => [
                  ...current,
                  {
                    id: nextTrackerFieldId(current),
                    label: "New field",
                    kind: "text",
                    required: false,
                    choices: [],
                  },
                ])
              }
            />
          </>
        ) : null}

        {kind === "plan" && original?.object_type === "plan" ? (
          <View style={styles.note}>
            <Text style={styles.noteText}>
              This edit preserves all {original.plan.items?.length ?? 0}{" "}
              existing plan items.
            </Text>
          </View>
        ) : null}
        {kind === "plan" ? (
          <View style={styles.fieldCard}>
            <Text accessibilityRole="header" style={styles.sectionTitle}>
              Plan items
            </Text>
            {planItems.length === 0 ? (
              <Text style={styles.noteText}>No intended items yet.</Text>
            ) : null}
            {planItems.map((item, index) => (
              <View key={item.id} style={styles.itemRow}>
                <View style={styles.cardMain}>
                  <Text style={styles.inputLabel}>{item.label}</Text>
                  <Text style={styles.noteText}>
                    {item.kind === "task"
                      ? "Manual task"
                      : `${item.kind} reference`}
                  </Text>
                </View>
                <View style={styles.actions}>
                  <ActionButton
                    label="Move up"
                    secondary
                    disabled={index === 0}
                    onPress={() => movePlanItem(index, -1)}
                  />
                  <ActionButton
                    label="Remove"
                    secondary
                    onPress={() =>
                      setPlanItems((current) =>
                        current.filter((_, itemIndex) => itemIndex !== index),
                      )
                    }
                  />
                  {editing &&
                  original?.object_type === "plan" &&
                  original.lifecycle === "active" &&
                  (original.plan.items ?? []).some(
                    (saved) => saved.id === item.id,
                  ) ? (
                    <ActionButton
                      label="Edit schedule"
                      secondary
                      onPress={() =>
                        router.push({
                          pathname: "/planning/schedule",
                          params: {
                            parentKind: "plan",
                            parentId: original.id,
                            itemId: item.id,
                            label: item.label,
                          },
                        })
                      }
                    />
                  ) : null}
                </View>
              </View>
            ))}
            <ChoiceField
              label="Item type"
              options={["task", "goal", "regimen"] as const}
              value={planItemKind}
              onChange={setPlanItemKind}
            />
            {planItemKind === "task" ? (
              <Input
                label="Task label"
                value={planItemLabel}
                onChange={setPlanItemLabel}
              />
            ) : (
              <View style={styles.inputGroup}>
                <Text style={styles.inputLabel}>Choose a goal or regimen</Text>
                {availableReferences
                  .filter(
                    (item) =>
                      item.object_type === planItemKind &&
                      item.status === "active",
                  )
                  .map((item) => (
                    <Pressable
                      key={item.id}
                      accessibilityRole="button"
                      accessibilityState={{
                        selected: planItemReference === item.id,
                      }}
                      onPress={() => {
                        setPlanItemReference(item.id);
                        setPlanItemLabel(item.title);
                      }}
                      style={[
                        styles.choice,
                        planItemReference === item.id && styles.choiceSelected,
                      ]}
                    >
                      <Text
                        style={[
                          styles.choiceText,
                          planItemReference === item.id &&
                            styles.choiceTextSelected,
                        ]}
                      >
                        {item.title}
                      </Text>
                    </Pressable>
                  ))}
                {availableReferences.filter(
                  (item) =>
                    item.object_type === planItemKind &&
                    item.status === "active",
                ).length === 0 ? (
                  <Text style={styles.noteText}>
                    Create an active {planItemKind} first.
                  </Text>
                ) : null}
                {pickerCursors[planItemKind] ? (
                  <ActionButton
                    label={`Load more ${planItemKind}s`}
                    secondary
                    busy={loadingPicker === planItemKind}
                    disabled={
                      loadingPicker !== null && loadingPicker !== planItemKind
                    }
                    onPress={() => void loadMorePicker(planItemKind)}
                  />
                ) : null}
              </View>
            )}
            <ActionButton
              label="Add plan item"
              secondary
              disabled={
                !planItemLabel.trim() ||
                (planItemKind !== "task" && !planItemReference) ||
                planItems.length >= 50
              }
              onPress={addPlanItem}
            />
          </View>
        ) : null}
        {kind === "context" ? (
          <View style={styles.note}>
            <Text style={styles.noteText}>
              Contexts are temporary relevance notes. They do not change Profile
              or pause a regimen.
            </Text>
          </View>
        ) : null}
        {kind === "regimen" ? (
          <>
            <View style={styles.note}>
              <Text style={styles.noteText}>
                Enter only instructions or quantities you choose. No dose or
                interaction advice is provided.
              </Text>
            </View>
            {editing &&
            original?.object_type === "regimen" &&
            original.lifecycle === "active" ? (
              <ActionButton
                label="Edit schedule"
                secondary
                onPress={() =>
                  router.push({
                    pathname: "/planning/schedule",
                    params: {
                      parentKind: "regimen",
                      parentId: original.id,
                      label: original.regimen.label,
                    },
                  })
                }
              />
            ) : null}
          </>
        ) : null}
        {editing && original ? (
          <ActionButton
            label="View revision history"
            secondary
            onPress={() =>
              router.push({
                pathname: "/planning/history",
                params: { kind: original.object_type, id: original.id },
              })
            }
          />
        ) : null}
        <ActionButton
          label={
            editing ? "Save changes" : `Create ${kindLabel(kind).toLowerCase()}`
          }
          busy={busy}
          disabled={conflictReloadRequired}
          onPress={() => void submit()}
        />
        <ActionButton
          label="Cancel"
          secondary
          disabled={busy}
          onPress={() => router.back()}
        />
      </ScrollView>
    </SafeAreaView>
  );

  function updateField(index: number, patch: Partial<TrackerField>) {
    setFields((current) =>
      current.map((field, fieldIndex) =>
        fieldIndex === index ? { ...field, ...patch } : field,
      ),
    );
  }

  function addPlanItem() {
    const item: components["schemas"]["PlanItemInput"] = {
      id: newDailyId(),
      kind: planItemKind,
      label: planItemLabel.trim(),
      reference_id: planItemKind === "task" ? null : planItemReference,
    };
    setPlanItems((current) => [...current, item]);
    setPlanItemLabel("");
    setPlanItemReference(null);
  }

  function movePlanItem(index: number, direction: -1 | 1) {
    setPlanItems((current) => {
      const destination = index + direction;
      if (destination < 0 || destination >= current.length) return current;
      const next = [...current];
      [next[index], next[destination]] = [next[destination], next[index]];
      return next;
    });
  }
}

function kindLabel(kind: string): string {
  return (
    (
      {
        goal: "goal",
        regimen: "regimen",
        plan: "plan",
        context: "context",
        tracker_definition: "tracker",
      } as Record<string, string>
    )[kind] ?? "planning item"
  );
}

function archivedDetails(item: PlanningItem): string {
  if (item.object_type === "goal") {
    const target = item.goal.target
      ? `${item.goal.target.comparator.replaceAll("_", " ")} ${item.goal.target.value} ${item.goal.target.unit} per ${item.goal.target_period ?? "once"}`
      : "No metric target";
    return `${item.goal.domain} · ${target}${item.goal.start_date ? ` · starts ${item.goal.start_date}` : ""}${item.goal.target_date ? ` · target date ${item.goal.target_date}` : ""}`;
  }
  if (item.object_type === "regimen") {
    const quantity = item.regimen.quantity
      ? ` · ${item.regimen.quantity.value} ${item.regimen.quantity.unit}`
      : "";
    return `${item.regimen.kind} · ${item.regimen.domain}${quantity}${item.regimen.instructions ? ` · ${item.regimen.instructions}` : ""}`;
  }
  if (item.object_type === "plan") {
    const items = (item.plan.items ?? [])
      .map((planItem) => planItem.label)
      .join(", ");
    return items || "No plan items";
  }
  if (item.object_type === "context") {
    const links = (item.context.related ?? [])
      .map((relation) => relation.object_id)
      .join(", ");
    return `${item.context.context_type} · priority ${item.context.priority ?? 0}${item.context.notes ? ` · ${item.context.notes}` : ""}${links ? ` · linked IDs: ${links}` : ""}`;
  }
  return `${item.definition.domain} · schema version ${item.current_schema_version} · ${item.definition.fields.length} fields`;
}

function isCalendarDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return (
    !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value
  );
}

function Input({
  label,
  value,
  onChange,
  keyboardType = "default",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  keyboardType?: "default" | "number-pad" | "decimal-pad";
}) {
  return (
    <View style={styles.inputGroup}>
      <Text style={styles.inputLabel}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        value={value}
        onChangeText={onChange}
        keyboardType={keyboardType}
        autoCapitalize="sentences"
        style={styles.input}
      />
    </View>
  );
}

function ChoiceField<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: readonly T[];
  value: string;
  onChange: (value: T) => void;
}) {
  return (
    <View style={styles.inputGroup}>
      <Text style={styles.inputLabel}>{label}</Text>
      <View style={styles.choices}>
        {options.map((option) => (
          <Pressable
            key={option}
            accessibilityRole="button"
            accessibilityState={{ selected: value === option }}
            onPress={() => onChange(option)}
            style={[styles.choice, value === option && styles.choiceSelected]}
          >
            <Text
              style={[
                styles.choiceText,
                value === option && styles.choiceTextSelected,
              ]}
            >
              {option.replaceAll("_", " ")}
            </Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: "#f7f9f7" },
  content: { gap: 16, padding: 20, paddingBottom: 36 },
  title: { color: "#17201c", fontSize: 28, fontWeight: "700" },
  subtitle: { color: "#46534d", fontSize: 15, lineHeight: 22 },
  sectionTitle: { color: "#203a2e", fontSize: 20, fontWeight: "700" },
  cardTitle: { color: "#17201c", fontSize: 18, fontWeight: "700" },
  body: { color: "#46534d", fontSize: 14, lineHeight: 20 },
  inputGroup: { gap: 6 },
  inputLabel: { color: "#203a2e", fontSize: 15, fontWeight: "700" },
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
  choices: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  choice: {
    backgroundColor: "#fff",
    borderColor: "#68786f",
    borderRadius: 18,
    borderWidth: 1,
    paddingHorizontal: 13,
    paddingVertical: 9,
  },
  choiceSelected: { backgroundColor: "#245d3a", borderColor: "#245d3a" },
  choiceText: { color: "#24342b", fontSize: 14, textTransform: "capitalize" },
  choiceTextSelected: { color: "#fff", fontWeight: "700" },
  fieldCard: {
    backgroundColor: "#eaf0ec",
    borderRadius: 14,
    gap: 12,
    padding: 14,
  },
  multiline: { minHeight: 90, paddingTop: 12, textAlignVertical: "top" },
  targetChoice: {
    backgroundColor: "#fff",
    borderRadius: 10,
    gap: 4,
    padding: 12,
  },
  targetChoiceSelected: { borderColor: "#245d3a", borderWidth: 2 },
  itemRow: { backgroundColor: "#fff", borderRadius: 10, gap: 10, padding: 12 },
  cardMain: { gap: 4 },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  note: { backgroundColor: "#eaf0ec", borderRadius: 12, padding: 14 },
  noteText: { color: "#46534d", fontSize: 14, lineHeight: 21 },
});
