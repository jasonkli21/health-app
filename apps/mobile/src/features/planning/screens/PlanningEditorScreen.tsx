import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { SafeAreaView, ScrollView, Text, View } from "react-native";
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
import { canAdvancePlanningRevision } from "../editState";
import { RequestScope } from "../../profile/requestScope";
import {
  buildPlanningMutation,
  GOAL_METRICS_BY_DOMAIN,
  planningCreateAttempt,
} from "../draft";
import type { PlanningKind as Kind, TrackerField } from "../draft";
import { ChoiceField, Input } from "../components/EditorControls";
import { styles } from "../components/editorStyles";
import {
  ContextEditorFields,
  GoalEditorFields,
  PlanDateFields,
  PlanItemsEditorFields,
  RegimenEditorFields,
  TrackerDefinitionFields,
  nextTrackerField,
} from "../components/PlanningKindSections";

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

    const built = buildPlanningMutation({
      kind,
      id: original?.id ?? newDailyId(),
      original,
      label,
      domain,
      category,
      startDate,
      endDate,
      targetDate,
      targetMetric,
      targetComparator,
      targetValue,
      targetUnit,
      targetPeriod,
      regimenQuantity,
      regimenUnit,
      regimenInstructions,
      contextNotes,
      contextPriority,
      contextRelated,
      fields,
      planItems,
      aiUseAllowed,
      crossDomainUseAllowed,
    });
    if (!built.ok) {
      setError(built.error);
      return;
    }

    setBusy(true);
    try {
      const { mutation } = built;
      if (editing) {
        switch (mutation.kind) {
          case "goal":
            await planningApi.updateGoal(
              { goal_id: mutation.create.id },
              mutation.update,
            );
            break;
          case "regimen":
            await planningApi.updateRegimen(
              { regimen_id: mutation.create.id },
              mutation.update,
            );
            break;
          case "plan":
            await planningApi.updatePlan(
              { plan_id: mutation.create.id },
              mutation.update,
            );
            break;
          case "context":
            await planningApi.updateContext(
              { context_id: mutation.create.id },
              mutation.update,
            );
            break;
          case "tracker_definition":
            await planningApi.updateTracker(
              { tracker_id: mutation.create.id },
              mutation.update,
            );
            break;
        }
      } else {
        const attempt = planningCreateAttempt(mutation, sessionAtSubmit);
        if (!(await sendCreate(attempt))) return;
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
          <GoalEditorFields
            domain={domain}
            startDate={startDate}
            targetDate={targetDate}
            targetMetric={targetMetric}
            targetComparator={targetComparator}
            targetValue={targetValue}
            targetUnit={targetUnit}
            targetPeriod={targetPeriod}
            onStartDate={setStartDate}
            onTargetDate={setTargetDate}
            onTargetMetric={setTargetMetric}
            onTargetComparator={setTargetComparator}
            onTargetValue={setTargetValue}
            onTargetUnit={setTargetUnit}
            onTargetPeriod={setTargetPeriod}
          />
        ) : null}
        {kind === "regimen" ? (
          <RegimenEditorFields
            category={category}
            quantity={regimenQuantity}
            unit={regimenUnit}
            instructions={regimenInstructions}
            startDate={startDate}
            endDate={endDate}
            units={TRACKER_UNITS}
            onCategory={setCategory}
            onQuantity={setRegimenQuantity}
            onUnit={setRegimenUnit}
            onInstructions={setRegimenInstructions}
            onStartDate={setStartDate}
            onEndDate={setEndDate}
          />
        ) : null}
        {kind === "plan" ? (
          <PlanDateFields
            startDate={startDate}
            endDate={endDate}
            onStartDate={setStartDate}
            onEndDate={setEndDate}
          />
        ) : null}
        {kind === "plan" ? (
          <PlanItemsEditorFields
            editing={editing}
            original={original}
            items={planItems}
            references={availableReferences}
            itemKind={planItemKind}
            itemLabel={planItemLabel}
            itemReference={planItemReference}
            pickerCursors={pickerCursors}
            loadingPicker={loadingPicker}
            onItemKind={setPlanItemKind}
            onItemLabel={setPlanItemLabel}
            onItemReference={setPlanItemReference}
            onRemove={(index) =>
              setPlanItems((current) =>
                current.filter((_, itemIndex) => itemIndex !== index),
              )
            }
            onMove={movePlanItem}
            onLoadMore={(targetKind) => void loadMorePicker(targetKind)}
            onAdd={addPlanItem}
            onEditSchedule={(item) =>
              original?.object_type === "plan" &&
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
        {kind === "context" ? (
          <ContextEditorFields
            category={category}
            startDate={startDate}
            endDate={endDate}
            priority={contextPriority}
            notes={contextNotes}
            related={contextRelated}
            targets={contextTargets}
            pickerCursors={pickerCursors}
            loadingPicker={loadingPicker}
            onCategory={setCategory}
            onStartDate={setStartDate}
            onEndDate={setEndDate}
            onPriority={setContextPriority}
            onNotes={setContextNotes}
            onRelated={setContextRelated}
            onLoadMore={(targetKind) => void loadMorePicker(targetKind)}
          />
        ) : null}
        {kind === "tracker_definition" ? (
          <TrackerDefinitionFields
            domain={domain}
            fields={fields}
            domains={TRACKER_DOMAINS}
            fieldKinds={FIELD_KINDS}
            units={TRACKER_UNITS}
            onDomain={setDomain}
            onUpdate={updateField}
            onRemove={(index) =>
              setFields((current) =>
                current.filter((_, fieldIndex) => fieldIndex !== index),
              )
            }
            onAdd={() =>
              setFields((current) => [...current, nextTrackerField(current)])
            }
          />
        ) : null}

        {kind === "plan" && original?.object_type === "plan" ? (
          <View style={styles.note}>
            <Text style={styles.noteText}>
              This edit preserves all {original.plan.items?.length ?? 0}{" "}
              existing plan items.
            </Text>
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
