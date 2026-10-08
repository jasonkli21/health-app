import { Pressable, Text, TextInput, View } from "react-native";
import type { components } from "@personal-health/api-client";

import { ActionButton } from "../../profile/components/Ui";
import type { PlanningItem } from "../api";
import { nextTrackerFieldId } from "../trackerEntry";
import { GOAL_METRICS_BY_DOMAIN, GOAL_UNITS } from "../draft";
import type { TrackerField } from "../draft";
import { ChoiceField, Input } from "./EditorControls";
import { styles } from "./editorStyles";

export function GoalEditorFields({
  domain,
  startDate,
  targetDate,
  targetMetric,
  targetComparator,
  targetValue,
  targetUnit,
  targetPeriod,
  onStartDate,
  onTargetDate,
  onTargetMetric,
  onTargetComparator,
  onTargetValue,
  onTargetUnit,
  onTargetPeriod,
}: {
  domain: string;
  startDate: string;
  targetDate: string;
  targetMetric: string;
  targetComparator: string;
  targetValue: string;
  targetUnit: string;
  targetPeriod: string;
  onStartDate: (value: string) => void;
  onTargetDate: (value: string) => void;
  onTargetMetric: (value: string) => void;
  onTargetComparator: (value: string) => void;
  onTargetValue: (value: string) => void;
  onTargetUnit: (value: string) => void;
  onTargetPeriod: (value: string) => void;
}) {
  return (
    <View style={styles.fieldCard}>
      <Text accessibilityRole="header" style={styles.sectionTitle}>
        Optional target
      </Text>
      <ChoiceField
        label="Metric"
        options={["none", ...(GOAL_METRICS_BY_DOMAIN[domain] ?? [])]}
        value={targetMetric}
        onChange={(metric) => {
          onTargetMetric(metric);
          const unit = GOAL_UNITS[metric]?.[0];
          if (unit) onTargetUnit(unit);
        }}
      />
      {targetMetric !== "none" ? (
        <>
          <ChoiceField
            label="Comparison"
            options={["at_least", "at_most", "equal"] as const}
            value={targetComparator}
            onChange={onTargetComparator}
          />
          <Input
            label="Target value"
            value={targetValue}
            onChange={onTargetValue}
            keyboardType="decimal-pad"
          />
          <ChoiceField
            label="Target unit"
            options={GOAL_UNITS[targetMetric] ?? []}
            value={targetUnit}
            onChange={onTargetUnit}
          />
          <ChoiceField
            label="Target period"
            options={["once", "day", "week", "month", "year"] as const}
            value={targetPeriod}
            onChange={onTargetPeriod}
          />
        </>
      ) : null}
      <Input
        label="Starts on (YYYY-MM-DD)"
        value={startDate}
        onChange={onStartDate}
      />
      <Input
        label="Target date (YYYY-MM-DD)"
        value={targetDate}
        onChange={onTargetDate}
      />
    </View>
  );
}

export function RegimenEditorFields({
  category,
  quantity,
  unit,
  instructions,
  startDate,
  endDate,
  units,
  onCategory,
  onQuantity,
  onUnit,
  onInstructions,
  onStartDate,
  onEndDate,
}: {
  category: string;
  quantity: string;
  unit: string;
  instructions: string;
  startDate: string;
  endDate: string;
  units: readonly string[];
  onCategory: (value: string) => void;
  onQuantity: (value: string) => void;
  onUnit: (value: string) => void;
  onInstructions: (value: string) => void;
  onStartDate: (value: string) => void;
  onEndDate: (value: string) => void;
}) {
  return (
    <View style={styles.fieldCard}>
      <ChoiceField
        label="Regimen type"
        options={["habit", "medication", "supplement", "activity"] as const}
        value={category}
        onChange={onCategory}
      />
      <Input
        label="Optional quantity"
        value={quantity}
        onChange={onQuantity}
        keyboardType="decimal-pad"
      />
      {quantity.trim() ? (
        <ChoiceField
          label="Quantity unit"
          options={units}
          value={unit}
          onChange={onUnit}
        />
      ) : null}
      <Text style={styles.inputLabel}>Optional instructions</Text>
      <TextInput
        accessibilityLabel="Optional instructions"
        value={instructions}
        onChangeText={onInstructions}
        multiline
        maxLength={2000}
        style={[styles.input, styles.multiline]}
      />
      <Input
        label="Starts on (YYYY-MM-DD)"
        value={startDate}
        onChange={onStartDate}
      />
      <Input
        label="Ends on (YYYY-MM-DD)"
        value={endDate}
        onChange={onEndDate}
      />
    </View>
  );
}

export function PlanDateFields({
  startDate,
  endDate,
  onStartDate,
  onEndDate,
}: {
  startDate: string;
  endDate: string;
  onStartDate: (value: string) => void;
  onEndDate: (value: string) => void;
}) {
  return (
    <View style={styles.fieldCard}>
      <Input
        label="Starts on (YYYY-MM-DD)"
        value={startDate}
        onChange={onStartDate}
      />
      <Input
        label="Ends on (YYYY-MM-DD)"
        value={endDate}
        onChange={onEndDate}
      />
    </View>
  );
}

export function ContextEditorFields({
  category,
  startDate,
  endDate,
  priority,
  notes,
  related,
  targets,
  pickerCursors,
  loadingPicker,
  onCategory,
  onStartDate,
  onEndDate,
  onPriority,
  onNotes,
  onRelated,
  onLoadMore,
}: {
  category: string;
  startDate: string;
  endDate: string;
  priority: string;
  notes: string;
  related: components["schemas"]["ContextRelation"][];
  targets: { id: string; title: string; kind: string }[];
  pickerCursors: Record<string, string | null>;
  loadingPicker: string | null;
  onCategory: (value: string) => void;
  onStartDate: (value: string) => void;
  onEndDate: (value: string) => void;
  onPriority: (value: string) => void;
  onNotes: (value: string) => void;
  onRelated: (
    update: (
      current: components["schemas"]["ContextRelation"][],
    ) => components["schemas"]["ContextRelation"][],
  ) => void;
  onLoadMore: (kind: "goal" | "regimen" | "profile") => void;
}) {
  return (
    <View style={styles.fieldCard}>
      <ChoiceField
        label="Context type"
        options={
          ["travel", "illness", "recovery", "schedule_change", "other"] as const
        }
        value={category}
        onChange={onCategory}
      />
      <Input
        label="Starts on (YYYY-MM-DD)"
        value={startDate}
        onChange={onStartDate}
      />
      <Input
        label="Ends on (YYYY-MM-DD)"
        value={endDate}
        onChange={onEndDate}
      />
      <Input
        label="Priority (0–100)"
        value={priority}
        onChange={onPriority}
        keyboardType="number-pad"
      />
      <Text style={styles.inputLabel}>Notes</Text>
      <TextInput
        accessibilityLabel="Context notes"
        value={notes}
        onChangeText={onNotes}
        multiline
        maxLength={2000}
        style={[styles.input, styles.multiline]}
      />
      <Text accessibilityRole="header" style={styles.inputLabel}>
        Related Profile items, goals, and regimens
      </Text>
      {targets.map((target) => {
        const selected = related.some(
          (relation) => relation.object_id === target.id,
        );
        return (
          <Pressable
            key={target.id}
            accessibilityRole="button"
            accessibilityState={{ selected }}
            onPress={() =>
              onRelated((current) =>
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
            disabled={loadingPicker !== null && loadingPicker !== targetKind}
            onPress={() => onLoadMore(targetKind)}
          />
        ) : null,
      )}
      {targets.length === 0 ? (
        <Text style={styles.noteText}>
          No Profile items, goals, or regimens are available to link.
        </Text>
      ) : null}
    </View>
  );
}

export function TrackerDefinitionFields({
  domain,
  fields,
  domains,
  fieldKinds,
  units,
  onDomain,
  onUpdate,
  onRemove,
  onAdd,
}: {
  domain: string;
  fields: TrackerField[];
  domains: readonly string[];
  fieldKinds: readonly string[];
  units: readonly string[];
  onDomain: (value: string) => void;
  onUpdate: (index: number, patch: Partial<TrackerField>) => void;
  onRemove: (index: number) => void;
  onAdd: () => void;
}) {
  return (
    <>
      <ChoiceField
        label="Tracker domain"
        options={domains}
        value={domain}
        onChange={onDomain}
      />
      <Text accessibilityRole="header" style={styles.sectionTitle}>
        Fields
      </Text>
      {fields.map((field, index) => (
        <View key={`${index}:${field.id}`} style={styles.fieldCard}>
          <Input
            label="Stable field ID"
            value={field.id}
            onChange={(value) => onUpdate(index, { id: value })}
          />
          <Input
            label="Field label"
            value={field.label}
            onChange={(value) => onUpdate(index, { label: value })}
          />
          <ChoiceField
            label="Field type"
            options={fieldKinds}
            value={field.kind}
            onChange={(value) =>
              onUpdate(index, {
                kind: value as TrackerField["kind"],
                choices: value === "enum" ? field.choices : [],
                unit: value === "quantity" ? (field.unit ?? "dose") : null,
              })
            }
          />
          {field.kind === "enum" ? (
            <Input
              label="Choices, separated by commas"
              value={(field.choices ?? []).join(", ")}
              onChange={(value) =>
                onUpdate(index, {
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
              options={units}
              value={field.unit ?? "dose"}
              onChange={(value) =>
                onUpdate(index, {
                  unit: value as TrackerField["unit"],
                })
              }
            />
          ) : null}
          <ActionButton
            label={field.required ? "Required: yes" : "Required: no"}
            secondary
            onPress={() => onUpdate(index, { required: !field.required })}
          />
          {fields.length > 1 ? (
            <ActionButton
              label="Remove field"
              secondary
              onPress={() => onRemove(index)}
            />
          ) : null}
        </View>
      ))}
      <ActionButton
        label="Add field"
        secondary
        disabled={fields.length >= 20}
        onPress={onAdd}
      />
    </>
  );
}

export function PlanItemsEditorFields({
  editing,
  original,
  items,
  references,
  itemKind,
  itemLabel,
  itemReference,
  pickerCursors,
  loadingPicker,
  onItemKind,
  onItemLabel,
  onItemReference,
  onRemove,
  onMove,
  onLoadMore,
  onAdd,
  onEditSchedule,
}: {
  editing: boolean;
  original: PlanningItem | null;
  items: components["schemas"]["PlanItemInput"][];
  references: PlanningItem[];
  itemKind: "task" | "goal" | "regimen";
  itemLabel: string;
  itemReference: string | null;
  pickerCursors: Record<string, string | null>;
  loadingPicker: string | null;
  onItemKind: (value: "task" | "goal" | "regimen") => void;
  onItemLabel: (value: string) => void;
  onItemReference: (value: string | null) => void;
  onRemove: (index: number) => void;
  onMove: (index: number, direction: -1 | 1) => void;
  onLoadMore: (kind: "goal" | "regimen") => void;
  onAdd: () => void;
  onEditSchedule: (item: components["schemas"]["PlanItemInput"]) => void;
}) {
  return (
    <View style={styles.fieldCard}>
      <Text accessibilityRole="header" style={styles.sectionTitle}>
        Plan items
      </Text>
      {items.length === 0 ? (
        <Text style={styles.noteText}>No intended items yet.</Text>
      ) : null}
      {items.map((item, index) => (
        <View key={item.id} style={styles.itemRow}>
          <View style={styles.cardMain}>
            <Text style={styles.inputLabel}>{item.label}</Text>
            <Text style={styles.noteText}>
              {item.kind === "task" ? "Manual task" : `${item.kind} reference`}
            </Text>
          </View>
          <View style={styles.actions}>
            <ActionButton
              label="Move up"
              secondary
              disabled={index === 0}
              onPress={() => onMove(index, -1)}
            />
            <ActionButton
              label="Remove"
              secondary
              onPress={() => onRemove(index)}
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
                onPress={() => onEditSchedule(item)}
              />
            ) : null}
          </View>
        </View>
      ))}
      <ChoiceField
        label="Item type"
        options={["task", "goal", "regimen"] as const}
        value={itemKind}
        onChange={onItemKind}
      />
      {itemKind === "task" ? (
        <Input label="Task label" value={itemLabel} onChange={onItemLabel} />
      ) : (
        <View style={styles.inputGroup}>
          <Text style={styles.inputLabel}>Choose a goal or regimen</Text>
          {references
            .filter(
              (item) =>
                item.object_type === itemKind && item.status === "active",
            )
            .map((item) => (
              <Pressable
                key={item.id}
                accessibilityRole="button"
                accessibilityState={{ selected: itemReference === item.id }}
                onPress={() => {
                  onItemReference(item.id);
                  onItemLabel(item.title);
                }}
                style={[
                  styles.choice,
                  itemReference === item.id && styles.choiceSelected,
                ]}
              >
                <Text
                  style={[
                    styles.choiceText,
                    itemReference === item.id && styles.choiceTextSelected,
                  ]}
                >
                  {item.title}
                </Text>
              </Pressable>
            ))}
          {references.filter(
            (item) => item.object_type === itemKind && item.status === "active",
          ).length === 0 ? (
            <Text style={styles.noteText}>
              Create an active {itemKind} first.
            </Text>
          ) : null}
          {pickerCursors[itemKind] ? (
            <ActionButton
              label={`Load more ${itemKind}s`}
              secondary
              busy={loadingPicker === itemKind}
              disabled={loadingPicker !== null && loadingPicker !== itemKind}
              onPress={() => onLoadMore(itemKind)}
            />
          ) : null}
        </View>
      )}
      <ActionButton
        label="Add plan item"
        secondary
        disabled={
          !itemLabel.trim() ||
          (itemKind !== "task" && !itemReference) ||
          items.length >= 50
        }
        onPress={onAdd}
      />
    </View>
  );
}

export function nextTrackerField(fields: TrackerField[]): TrackerField {
  return {
    id: nextTrackerFieldId(fields),
    label: "New field",
    kind: "text",
    required: false,
    choices: [],
  };
}
