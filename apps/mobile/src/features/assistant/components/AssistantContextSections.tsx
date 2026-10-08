import { Switch, Text, TextInput, View } from "react-native";
import { Link } from "expo-router";
import type { components } from "@personal-health/api-client";

import { Button, Choice, ErrorMessage } from "./AssistantControls";
import { styles } from "./assistantStyles";
import type { ResourceType, TaskKind } from "../state";

const RESOURCE_TYPES: { value: ResourceType; label: string }[] = [
  { value: "profile_item", label: "Profile" },
  { value: "event", label: "Events" },
  { value: "observation", label: "Observations" },
  { value: "goal", label: "Goals" },
  { value: "regimen", label: "Regimens" },
  { value: "plan", label: "Plans" },
  { value: "context", label: "Contexts" },
];

const TASK_KINDS: { value: TaskKind; label: string }[] = [
  { value: "general_wellness", label: "General wellness" },
  { value: "education", label: "Education" },
  { value: "understand_health_data", label: "Understand my health data" },
  { value: "consequential_medical", label: "Medical decision" },
  { value: "urgent_safety", label: "Urgent safety concern" },
];

const RESOURCE_DOMAINS = [
  "nutrition",
  "exercise",
  "sleep",
  "symptoms",
  "measurements",
  "general",
] as const;

const LOOKBACK_OPTIONS = [7, 30, 90] as const;

function typeLabel(value: string): string {
  return RESOURCE_TYPES.find((item) => item.value === value)?.label ?? value;
}

function timeLabel(value: Record<string, unknown> | undefined): string | null {
  if (!value) return null;
  const timezone =
    typeof value.timezone === "string" ? value.timezone : "timezone unknown";
  if (value.precision === "date_only" && typeof value.local_date === "string") {
    return `${value.local_date} · date only · ${timezone}`;
  }
  if (value.precision === "instant" && typeof value.occurred_at === "string") {
    const end =
      typeof value.ended_at === "string" ? ` – ${value.ended_at}` : "";
    return `${value.occurred_at}${end} · ${timezone}`;
  }
  return "Time not recorded";
}

function readablePayload(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

export function ContextScopeSection({
  resourceTypes,
  domains,
  task,
  taskKind,
  lookbackDays,
  busy,
  onResourceType,
  onToggleDomain,
  onTask,
  onTaskKind,
  onLookbackDays,
  onPreview,
}: {
  resourceTypes: ResourceType[];
  domains: string[];
  task: string;
  taskKind: TaskKind;
  lookbackDays: 7 | 30 | 90;
  busy: boolean;
  onResourceType: (type: ResourceType, enabled: boolean) => void;
  onToggleDomain: (domain: string) => void;
  onTask: (value: string) => void;
  onTaskKind: (value: TaskKind) => void;
  onLookbackDays: (days: 7 | 30 | 90) => void;
  onPreview: () => void;
}) {
  return (
    <View style={styles.section}>
      <Text accessibilityRole="header" style={styles.sectionTitle}>
        Choose context scope
      </Text>
      <Text style={styles.hint}>
        Selecting a type narrows the preview. It never turns on an item’s
        permission.
      </Text>
      {RESOURCE_TYPES.map((item) => (
        <View key={item.value} style={styles.switchRow}>
          <Text style={styles.switchLabel}>{item.label}</Text>
          <Switch
            accessibilityLabel={`Include ${item.label} in context preview`}
            accessibilityHint="Items must also have their own AI use permission enabled."
            value={resourceTypes.includes(item.value)}
            onValueChange={(enabled) => onResourceType(item.value, enabled)}
          />
        </View>
      ))}

      <Text style={styles.fieldLabel}>Limit to domains (optional)</Text>
      <Text style={styles.hint}>
        An empty selection includes all domains represented by the selected
        types.
      </Text>
      <View style={styles.choiceRow}>
        {RESOURCE_DOMAINS.map((domain) => (
          <Choice
            key={domain}
            label={domain}
            selected={domains.includes(domain)}
            onPress={() => onToggleDomain(domain)}
          />
        ))}
      </View>

      <Text style={styles.fieldLabel}>
        What should the Assistant help with?
      </Text>
      <TextInput
        accessibilityLabel="Context task"
        accessibilityHint="Used to rank relevant items in the local context preview. Up to 300 characters."
        value={task}
        onChangeText={onTask}
        maxLength={300}
        placeholder="For example, summarize my recent sleep"
        style={styles.input}
      />

      <Text style={styles.fieldLabel}>Task category</Text>
      <View style={styles.choiceRow}>
        {TASK_KINDS.map((item) => (
          <Choice
            key={item.value}
            label={item.label}
            selected={taskKind === item.value}
            onPress={() => onTaskKind(item.value)}
          />
        ))}
      </View>

      <Text style={styles.fieldLabel}>Recent daily entries</Text>
      <View style={styles.choiceRow}>
        {LOOKBACK_OPTIONS.map((days) => (
          <Choice
            key={days}
            label={`${days} days`}
            selected={lookbackDays === days}
            onPress={() => onLookbackDays(days)}
          />
        ))}
      </View>

      <Button
        label={busy ? "Working…" : "Preview selected context"}
        disabled={busy || resourceTypes.length === 0}
        onPress={onPreview}
      />
    </View>
  );
}

export function ContextPreviewSection({
  pack,
  previewIsCurrent,
  error,
  excludedObjectIds,
  onToggleExcluded,
}: {
  pack: components["schemas"]["AIContextPack"] | null;
  previewIsCurrent: boolean;
  error: string | null;
  excludedObjectIds: string[];
  onToggleExcluded: (objectId: string) => void;
}) {
  return (
    <>
      {error ? <ErrorMessage message={error} /> : null}
      {pack ? (
        <View style={styles.section}>
          <Text accessibilityRole="header" style={styles.sectionTitle}>
            Included items ({pack.entries.length})
          </Text>
          {!previewIsCurrent ? (
            <Text style={styles.warning}>
              Scope changed. Refresh the preview before relying on this list.
            </Text>
          ) : null}
          <Text style={styles.hint}>
            {pack.included_counts && Object.entries(pack.included_counts).length
              ? Object.entries(pack.included_counts)
                  .map(([type, count]) => `${typeLabel(type)}: ${count}`)
                  .join(" · ")
              : "No eligible items matched this scope."}
            {pack.truncated
              ? " · Preview was truncated to its safety budget."
              : ""}
          </Text>
          {pack.today_summaries.length ? (
            <View style={styles.summaryCard}>
              <Text style={styles.entryTitle}>
                Today summary · {pack.today_summary_date}
              </Text>
              <Text style={styles.hint}>
                Calculated from included, opted-in entries only. Coverage does
                not describe records outside this preview.
              </Text>
              {pack.today_summaries.map((summary) => (
                <Text
                  key={`${summary.domain}:${summary.metric}`}
                  style={styles.summaryText}
                >
                  {summary.domain} · {summary.metric}:{" "}
                  {summary.known_value === null
                    ? "Unknown"
                    : summary.known_value}{" "}
                  {summary.unit} · coverage {summary.coverage.known_count}/
                  {summary.coverage.total_count}
                </Text>
              ))}
            </View>
          ) : null}
          {pack.entries.map((entry) => (
            <View
              key={`${entry.object_id}:${entry.revision}`}
              style={styles.entry}
            >
              <Text style={styles.entryTitle}>{entry.title}</Text>
              <Text style={styles.hint}>
                {typeLabel(entry.object_type)} · {entry.source_kind} · revision{" "}
                {entry.revision} · {entry.confirmation_status}
              </Text>
              <Text style={styles.hint}>{entry.relevance_reason}</Text>
              {timeLabel(
                entry.content.time as Record<string, unknown> | undefined,
              ) ? (
                <Text style={styles.hint}>
                  Source time:{" "}
                  {timeLabel(entry.content.time as Record<string, unknown>)}
                </Text>
              ) : null}
              {entry.valid_from || entry.valid_to ? (
                <Text style={styles.hint}>
                  Validity: {entry.valid_from ?? "open"} to{" "}
                  {entry.valid_to ?? "open"}
                </Text>
              ) : null}
              <Choice
                label={
                  excludedObjectIds.includes(entry.object_id)
                    ? "Include for this request"
                    : "Exclude from this request"
                }
                selected={excludedObjectIds.includes(entry.object_id)}
                onPress={() => onToggleExcluded(entry.object_id)}
              />
              <Text selectable style={styles.payload}>
                {readablePayload(entry.content.payload)}
              </Text>
              {entry.object_type === "event" ||
              entry.object_type === "observation" ? (
                <Link
                  accessibilityRole="button"
                  style={styles.textLink}
                  href={{
                    pathname: "/daily/item/[itemId]",
                    params: {
                      itemId: entry.object_id,
                      type: entry.object_type,
                    },
                  }}
                >
                  Open source entry
                </Link>
              ) : null}
              {typeof entry.content.notes === "string" &&
              entry.content.notes ? (
                <Text style={styles.hint}>Note: {entry.content.notes}</Text>
              ) : null}
            </View>
          ))}
        </View>
      ) : null}
    </>
  );
}

export function AssistantSearchSection({
  searchText,
  currentSearchKey,
  error,
  errorKey,
  stale,
  results,
  cursor,
  busy,
  resourceTypeCount,
  onSearchText,
  onSearch,
}: {
  searchText: string;
  currentSearchKey: string;
  error: string | null;
  errorKey: string | null;
  stale: boolean;
  results: components["schemas"]["AISearchResult"][];
  cursor: string | null;
  busy: boolean;
  resourceTypeCount: number;
  onSearchText: (value: string) => void;
  onSearch: (append: boolean) => void;
}) {
  return (
    <View style={styles.section}>
      <Text accessibilityRole="header" style={styles.sectionTitle}>
        Search AI-eligible items
      </Text>
      <Text style={styles.hint}>
        Search is owner-scoped and returns only current items with AI use
        permission enabled. Select one or more resource types above to set the
        search scope.
      </Text>
      <TextInput
        accessibilityLabel="Search eligible health items"
        value={searchText}
        onChangeText={onSearchText}
        maxLength={500}
        placeholder="Search selected health items"
        style={styles.input}
      />
      <Button
        label="Search"
        disabled={busy || !searchText.trim() || resourceTypeCount === 0}
        onPress={() => onSearch(false)}
      />
      {errorKey === currentSearchKey && error ? (
        <ErrorMessage message={error} />
      ) : null}
      {stale && results.length ? (
        <Text style={styles.warning}>
          These results may be stale. Search again to refresh them.
        </Text>
      ) : null}
      {results.map((item) => (
        <View key={`${item.object_id}:${item.revision}`} style={styles.entry}>
          <Text style={styles.entryTitle}>{item.title}</Text>
          <Text style={styles.hint}>
            {typeLabel(item.object_type)} · revision {item.revision} ·{" "}
            {item.confirmation_status}
          </Text>
          <Text style={styles.payload}>{item.excerpt}</Text>
          {item.time_precision === "date_only" && item.local_date ? (
            <Text style={styles.hint}>
              Source date: {item.local_date} · date only ·{" "}
              {item.timezone ?? "timezone unknown"}
            </Text>
          ) : null}
          {item.time_precision === "instant" && item.occurred_at ? (
            <Text style={styles.hint}>
              Source time: {item.occurred_at}
              {item.interval_end ? ` – ${item.interval_end}` : ""} ·{" "}
              {item.timezone ?? "timezone unknown"}
            </Text>
          ) : null}
          {item.valid_from || item.valid_to ? (
            <Text style={styles.hint}>
              Validity: {item.valid_from ?? "open"} to {item.valid_to ?? "open"}
            </Text>
          ) : null}
          {item.object_type === "event" ||
          item.object_type === "observation" ? (
            <Link
              accessibilityRole="button"
              style={styles.textLink}
              href={{
                pathname: "/daily/item/[itemId]",
                params: { itemId: item.object_id, type: item.object_type },
              }}
            >
              Open source entry
            </Link>
          ) : null}
        </View>
      ))}
      {cursor ? (
        <Button
          label="Load more search results"
          disabled={busy}
          onPress={() => onSearch(true)}
        />
      ) : null}
    </View>
  );
}

export function AssistantMessageSection({
  status,
  message,
  resourceTypeCount,
  busy,
  reply,
  onMessage,
  onSend,
}: {
  status: components["schemas"]["AssistantStatusResponse"] | null;
  message: string;
  resourceTypeCount: number;
  busy: boolean;
  reply: components["schemas"]["AssistantMessageResponse"] | null;
  onMessage: (value: string) => void;
  onSend: () => void;
}) {
  return (
    <View style={styles.section}>
      <Text accessibilityRole="header" style={styles.sectionTitle}>
        Ask a question
      </Text>
      <TextInput
        accessibilityLabel="Assistant message"
        accessibilityHint="Up to 8,000 characters. Your draft stays in memory on this screen."
        value={message}
        onChangeText={onMessage}
        maxLength={8000}
        multiline
        placeholder="Ask about the context you selected"
        style={[styles.input, styles.multiline]}
      />
      <Button
        label="Send to Assistant"
        disabled={
          busy || !status?.enabled || !message.trim() || resourceTypeCount === 0
        }
        onPress={onSend}
      />
      {!status?.enabled ? (
        <Text style={styles.hint}>
          Sending is disabled until the Personal AI service, delegation, and
          data-retention contracts are reviewed and configured.
        </Text>
      ) : null}
      {reply ? (
        <View style={styles.entry}>
          <Text style={styles.entryTitle}>Assistant reply</Text>
          <Text style={styles.body}>{reply.reply}</Text>
          <Text style={styles.hint}>Risk class: {reply.risk_class}</Text>
          <Text style={styles.hint}>
            Evidence: {reply.evidence_refs.length} revision-linked source(s)
          </Text>
          {reply.evidence_refs.map((reference) =>
            reference.object_type && reference.title ? (
              <Link
                key={`${reference.object_id}:${reference.revision}`}
                accessibilityRole="button"
                style={styles.textLink}
                href={
                  reference.object_type === "event" ||
                  reference.object_type === "observation"
                    ? {
                        pathname: "/daily/item/[itemId]",
                        params: {
                          itemId: reference.object_id,
                          type: reference.object_type,
                        },
                      }
                    : reference.object_type === "profile_item"
                      ? "/profile"
                      : "/planning"
                }
              >
                {reference.title} · revision {reference.revision}
              </Link>
            ) : (
              <Text
                key={`${reference.object_id}:${reference.revision}`}
                style={styles.hint}
              >
                Source unavailable · revision {reference.revision}
              </Text>
            ),
          )}
        </View>
      ) : null}
    </View>
  );
}
