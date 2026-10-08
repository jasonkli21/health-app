import type { Dispatch, SetStateAction } from "react";
import { Text, View } from "react-native";
import type { components } from "@personal-health/api-client";

import { ActionButton } from "../../profile/components/Ui";
import {
  SelectButton,
  ValueField,
  formatInsightValue,
} from "./InsightsControls";
import { styles } from "./insightsStyles";

type Metric = components["schemas"]["MetricDefinition"];
type Experiment = components["schemas"]["ExperimentResponse"];
type ExperimentForm = components["schemas"]["ExperimentPayloadV1"];
type ExperimentResult = components["schemas"]["ExperimentResult"];

export function ExperimentsSection({
  metrics,
  form,
  editing,
  pendingCreate,
  experiments,
  results,
  cursor,
  busy,
  onFormChange,
  onSave,
  onCancel,
  onDiscardPending,
  onEdit,
  onTransition,
  onLoadResult,
  onLoadMore,
}: {
  metrics: Metric[];
  form: ExperimentForm;
  editing: Experiment | null;
  pendingCreate: boolean;
  experiments: Experiment[];
  results: Record<string, ExperimentResult>;
  cursor: string | null;
  busy: boolean;
  onFormChange: Dispatch<SetStateAction<ExperimentForm>>;
  onSave: () => void;
  onCancel: () => void;
  onDiscardPending: () => void;
  onEdit: (item: Experiment) => void;
  onTransition: (
    item: Experiment,
    state: "active" | "completed" | "stopped" | "archived",
  ) => void;
  onLoadResult: (item: Experiment) => void;
  onLoadMore: () => void;
}) {
  const selectedOutcomeMetric = metrics.find(
    (item) => item.metric === form.outcome_metric,
  );
  const designLocked = editing !== null && editing.state !== "draft";

  return (
    <View style={styles.section}>
      <Text accessibilityRole="header" style={styles.sectionTitle}>
        {designLocked
          ? "Edit experiment notes"
          : editing
            ? "Edit experiment draft"
            : "Manual experiment"}
      </Text>
      <Text style={styles.help}>
        You set the hypothesis, intervention and outcome. The comparison is
        descriptive and does not establish causation.
      </Text>
      <ValueField
        label="Hypothesis"
        value={form.hypothesis}
        onChange={(value) =>
          onFormChange((current) => ({ ...current, hypothesis: value }))
        }
        multiline
        disabled={designLocked}
      />
      <ValueField
        label="What you plan to try"
        value={form.intervention}
        onChange={(value) =>
          onFormChange((current) => ({ ...current, intervention: value }))
        }
        multiline
        disabled={designLocked}
      />
      <Text style={styles.fieldLabel}>
        Outcome metric: {selectedOutcomeMetric?.label ?? "choose below"} (
        {selectedOutcomeMetric?.unit ?? ""})
      </Text>
      <View style={styles.choices}>
        {metrics.map((item) => (
          <SelectButton
            key={`outcome:${item.metric}`}
            label={`${item.label} · ${item.unit}`}
            selected={form.outcome_metric === item.metric}
            disabled={designLocked}
            onPress={() =>
              onFormChange((current) => ({
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
            onFormChange((current) => ({ ...current, baseline_start: value }))
          }
          placeholder="YYYY-MM-DD"
          disabled={designLocked}
        />
        <ValueField
          label="Intervention starts"
          value={form.start_date}
          onChange={(value) =>
            onFormChange((current) => ({ ...current, start_date: value }))
          }
          placeholder="YYYY-MM-DD"
          disabled={designLocked}
        />
        <ValueField
          label="Intervention ends"
          value={form.end_date}
          onChange={(value) =>
            onFormChange((current) => ({ ...current, end_date: value }))
          }
          placeholder="YYYY-MM-DD"
          disabled={designLocked}
        />
      </View>
      <ValueField
        label="Notes"
        value={form.notes ?? ""}
        onChange={(value) =>
          onFormChange((current) => ({ ...current, notes: value }))
        }
        multiline
      />
      {pendingCreate ? (
        <View style={styles.row}>
          <Text style={styles.help}>
            The last create response was uncertain. Retry sends the same ID and
            content; discard it before saving edited fields.
          </Text>
          <ActionButton
            label="Discard uncertain save"
            secondary
            onPress={onDiscardPending}
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
          onPress={onSave}
        />
        {editing ? (
          <ActionButton label="Cancel edit" secondary onPress={onCancel} />
        ) : null}
      </View>

      {experiments.map((item) => (
        <View key={item.id} style={styles.card}>
          <Text style={styles.cardTitle}>{item.title}</Text>
          <Text style={styles.help}>
            {item.state} · {item.experiment.baseline_start} to{" "}
            {item.experiment.end_date} · {item.experiment.outcome_metric}
            {item.experiment.actual_end_at
              ? ` · ended ${new Date(item.experiment.actual_end_at).toLocaleString()}`
              : ""}
          </Text>
          <Text style={styles.cardBody}>{item.experiment.hypothesis}</Text>
          {item.state === "draft" && !pendingCreate ? (
            <ActionButton
              label="Edit draft"
              secondary
              onPress={() => onEdit(item)}
            />
          ) : null}
          {(["active", "completed", "stopped"] as const).includes(
            item.state as "active" | "completed" | "stopped",
          ) ? (
            <ActionButton
              label="Edit notes"
              secondary
              onPress={() => onEdit(item)}
            />
          ) : null}
          <View style={styles.row}>
            {item.state === "draft" ? (
              <ActionButton
                label="Start manually"
                secondary
                busy={busy}
                onPress={() => onTransition(item, "active")}
              />
            ) : null}
            {item.state === "active" ? (
              <>
                <ActionButton
                  label="Complete"
                  secondary
                  busy={busy}
                  onPress={() => onTransition(item, "completed")}
                />
                <ActionButton
                  label="Stop"
                  secondary
                  busy={busy}
                  onPress={() => onTransition(item, "stopped")}
                />
              </>
            ) : null}
            {item.state === "completed" || item.state === "stopped" ? (
              <ActionButton
                label="Archive"
                secondary
                busy={busy}
                onPress={() => onTransition(item, "archived")}
              />
            ) : null}
            {(["active", "completed", "stopped"] as const).includes(
              item.state as "active" | "completed" | "stopped",
            ) ? (
              <ActionButton
                label="View descriptive results"
                secondary
                busy={busy}
                onPress={() => onLoadResult(item)}
              />
            ) : null}
          </View>
          {results[item.id] ? (
            <ExperimentResultDetails item={item} result={results[item.id]} />
          ) : null}
        </View>
      ))}
      {cursor ? (
        <ActionButton
          label="Load more experiment history"
          secondary
          busy={busy}
          onPress={onLoadMore}
        />
      ) : null}
    </View>
  );
}

function ExperimentResultDetails({
  item,
  result,
}: {
  item: Experiment;
  result: ExperimentResult;
}) {
  return (
    <View style={styles.result}>
      <Text style={styles.help}>Calendar timezone: {result.timezone}</Text>
      <Text style={styles.help}>
        Planned through {item.experiment.end_date}; observed through{" "}
        {result.intervention.to_date}.
      </Text>
      <Text style={styles.cardBody}>
        Baseline ({result.baseline.known_days} known,{" "}
        {result.baseline.missing_days} missing):{" "}
        {formatInsightValue(result.baseline.mean, result.unit)}
      </Text>
      <Text style={styles.cardBody}>
        Intervention ({result.intervention.known_days} known,{" "}
        {result.intervention.missing_days} missing):{" "}
        {formatInsightValue(result.intervention.mean, result.unit)}
      </Text>
      <Text style={styles.help}>
        Difference: {formatInsightValue(result.mean_difference, result.unit)} ·{" "}
        {result.limitation}
      </Text>
    </View>
  );
}
