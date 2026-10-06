import { useCallback, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from "react-native";
import { Link, useFocusEffect } from "expo-router";

import type { components } from "@personal-health/api-client";
import { ApiError } from "@personal-health/api-client";
import { assistantApi } from "../api";

type ResourceType =
  components["schemas"]["AIContextRequest"]["resource_types"][number];
type TaskKind = NonNullable<
  components["schemas"]["AIContextRequest"]["task_kind"]
>;

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

const LOOKBACK_OPTIONS = [7, 30, 90] as const;

function requestMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return (
      error.body?.message ?? "The Assistant request could not be completed."
    );
  }
  return "Could not reach your Health API. Check the connection and try again.";
}

function typeLabel(value: string): string {
  return RESOURCE_TYPES.find((item) => item.value === value)?.label ?? value;
}

export default function AssistantScreen() {
  const [status, setStatus] = useState<
    components["schemas"]["AssistantStatusResponse"] | null
  >(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [resourceTypes, setResourceTypes] = useState<ResourceType[]>([]);
  const [task, setTask] = useState("");
  const [taskKind, setTaskKind] = useState<TaskKind>("general_wellness");
  const [lookbackDays, setLookbackDays] =
    useState<(typeof LOOKBACK_OPTIONS)[number]>(30);
  const [message, setMessage] = useState("");
  const [pack, setPack] = useState<
    components["schemas"]["AIContextPack"] | null
  >(null);
  const [previewKey, setPreviewKey] = useState<string | null>(null);
  const [reply, setReply] = useState<
    components["schemas"]["AssistantMessageResponse"] | null
  >(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [searchText, setSearchText] = useState("");
  const [searchResults, setSearchResults] = useState<
    components["schemas"]["AISearchResult"][]
  >([]);
  const [searchCursor, setSearchCursor] = useState<string | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const scopeTask =
    task.trim() ||
    message.trim().slice(0, 300) ||
    "Review my selected health data";
  const scope = useMemo<components["schemas"]["AIContextRequest"]>(
    () => ({
      task: scopeTask.slice(0, 300),
      task_kind: taskKind,
      resource_types: resourceTypes,
      lookback_days: lookbackDays,
    }),
    [lookbackDays, resourceTypes, scopeTask, taskKind],
  );
  const currentScopeKey = JSON.stringify(scope);
  const previewIsCurrent = previewKey === currentScopeKey;

  const loadStatus = useCallback(async () => {
    try {
      setStatusError(null);
      setStatus(await assistantApi.getAssistantStatus());
    } catch (error) {
      setStatusError(requestMessage(error));
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void loadStatus();
    }, [loadStatus]),
  );

  function toggleResourceType(resourceType: ResourceType, enabled: boolean) {
    setResourceTypes((current) =>
      enabled
        ? [...current, resourceType]
        : current.filter((value) => value !== resourceType),
    );
    setReply(null);
  }

  async function previewContext() {
    if (resourceTypes.length === 0) {
      setPreviewError(
        "Choose at least one type of health information to preview.",
      );
      return;
    }
    setBusy(true);
    setPreviewError(null);
    setReply(null);
    try {
      const result = await assistantApi.previewAIContext(scope);
      setPack(result);
      setPreviewKey(currentScopeKey);
    } catch (error) {
      setPreviewError(requestMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function search(append = false) {
    if (!searchText.trim()) {
      setSearchError("Enter a word or phrase to search.");
      return;
    }
    setBusy(true);
    setSearchError(null);
    try {
      const result = await assistantApi.searchAIEligibleHealthData({
        q: searchText.trim(),
        types: resourceTypes.length ? resourceTypes.join(",") : undefined,
        limit: 20,
        cursor: append ? searchCursor : undefined,
      });
      setSearchResults((current) =>
        append ? [...current, ...result.items] : result.items,
      );
      setSearchCursor(result.next_cursor);
    } catch (error) {
      setSearchError(requestMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function sendMessage() {
    if (!status?.enabled || !message.trim() || resourceTypes.length === 0)
      return;
    setBusy(true);
    setPreviewError(null);
    setReply(null);
    try {
      const result = await assistantApi.sendAssistantMessage({
        message: message.trim(),
        scope,
      });
      setReply(result);
    } catch (error) {
      setPreviewError(requestMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <Text accessibilityRole="header" style={styles.title}>
        Assistant
      </Text>
      <Text style={styles.body}>
        Review the exact Health items selected for a future read-only Assistant
        request. Suggestions cannot save or change health records.
      </Text>

      {status ? (
        <View style={[styles.statusCard, status.enabled && styles.readyCard]}>
          <Text accessibilityRole="header" style={styles.sectionTitle}>
            {status.enabled ? "Assistant available" : "Assistant unavailable"}
          </Text>
          <Text style={styles.body}>{status.message}</Text>
        </View>
      ) : statusError ? (
        <View style={styles.errorCard}>
          <Text accessibilityRole="alert" style={styles.errorText}>
            {statusError}
          </Text>
          <Button label="Retry status" onPress={() => void loadStatus()} />
        </View>
      ) : (
        <View style={styles.statusCard}>
          <ActivityIndicator accessibilityLabel="Loading Assistant status" />
        </View>
      )}

      <View style={styles.notice}>
        <Text accessibilityRole="header" style={styles.sectionTitle}>
          Your data controls
        </Text>
        <Text style={styles.body}>
          Preview includes only active, current items whose individual “Allow AI
          use” permission is on. This build has no configured Personal AI
          service, so it sends no health information outside Health. You can
          change item permissions in Profile, Plan, and each daily entry’s edit
          form.
        </Text>
        <View style={styles.linkRow}>
          <Link
            accessibilityRole="button"
            style={styles.textLink}
            href="/profile"
          >
            Open Profile
          </Link>
          <Link
            accessibilityRole="button"
            style={styles.textLink}
            href="/planning"
          >
            Open Plan
          </Link>
          <Link
            accessibilityRole="button"
            style={styles.textLink}
            href="/today"
          >
            Open Today
          </Link>
        </View>
      </View>

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
              onValueChange={(enabled) =>
                toggleResourceType(item.value, enabled)
              }
            />
          </View>
        ))}

        <Text style={styles.fieldLabel}>
          What should the Assistant help with?
        </Text>
        <TextInput
          accessibilityLabel="Context task"
          accessibilityHint="Used to rank relevant items in the local context preview. Up to 300 characters."
          value={task}
          onChangeText={setTask}
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
              onPress={() => setTaskKind(item.value)}
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
              onPress={() => setLookbackDays(days)}
            />
          ))}
        </View>

        <Button
          label={busy ? "Working…" : "Preview selected context"}
          disabled={busy || resourceTypes.length === 0}
          onPress={() => void previewContext()}
        />
      </View>

      {previewError ? <ErrorMessage message={previewError} /> : null}
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
              <Text selectable style={styles.payload}>
                {JSON.stringify(entry.content.payload)}
              </Text>
              {typeof entry.content.notes === "string" &&
              entry.content.notes ? (
                <Text style={styles.hint}>Note: {entry.content.notes}</Text>
              ) : null}
            </View>
          ))}
        </View>
      ) : null}

      <View style={styles.section}>
        <Text accessibilityRole="header" style={styles.sectionTitle}>
          Search AI-eligible items
        </Text>
        <Text style={styles.hint}>
          Search is owner-scoped and returns only current items with AI use
          permission enabled.
        </Text>
        <TextInput
          accessibilityLabel="Search eligible health items"
          value={searchText}
          onChangeText={setSearchText}
          maxLength={500}
          placeholder="Search selected health items"
          style={styles.input}
        />
        <Button
          label="Search"
          disabled={busy || !searchText.trim()}
          onPress={() => void search(false)}
        />
        {searchError ? <ErrorMessage message={searchError} /> : null}
        {searchResults.map((item) => (
          <View key={`${item.object_id}:${item.revision}`} style={styles.entry}>
            <Text style={styles.entryTitle}>{item.title}</Text>
            <Text style={styles.hint}>
              {typeLabel(item.object_type)} · revision {item.revision} ·{" "}
              {item.confirmation_status}
            </Text>
            <Text style={styles.payload}>{item.excerpt}</Text>
          </View>
        ))}
        {searchCursor ? (
          <Button
            label="Load more search results"
            disabled={busy}
            onPress={() => void search(true)}
          />
        ) : null}
      </View>

      <View style={styles.section}>
        <Text accessibilityRole="header" style={styles.sectionTitle}>
          Ask a question
        </Text>
        <TextInput
          accessibilityLabel="Assistant message"
          accessibilityHint="Up to 8,000 characters. Your draft stays in memory on this screen."
          value={message}
          onChangeText={setMessage}
          maxLength={8000}
          multiline
          placeholder="Ask about the context you selected"
          style={[styles.input, styles.multiline]}
        />
        <Button
          label="Send to Assistant"
          disabled={
            busy ||
            !status?.enabled ||
            !message.trim() ||
            resourceTypes.length === 0
          }
          onPress={() => void sendMessage()}
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
          </View>
        ) : null}
      </View>
    </ScrollView>
  );
}

function Button({
  label,
  onPress,
  disabled = false,
}: {
  label: string;
  onPress: () => void;
  disabled?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled, busy: disabled && label === "Working…" }}
      disabled={disabled}
      onPress={onPress}
      style={[styles.button, disabled && styles.disabled]}
    >
      <Text style={styles.buttonText}>{label}</Text>
    </Pressable>
  );
}

function Choice({
  label,
  selected,
  onPress,
}: {
  label: string;
  selected: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityLabel={label}
      accessibilityState={{ checked: selected }}
      onPress={onPress}
      style={[styles.choice, selected && styles.choiceSelected]}
    >
      <Text style={[styles.choiceText, selected && styles.choiceTextSelected]}>
        {label}
      </Text>
    </Pressable>
  );
}

function ErrorMessage({ message }: { message: string }) {
  return (
    <Text
      accessibilityRole="alert"
      accessibilityLiveRegion="polite"
      style={styles.errorText}
    >
      {message}
    </Text>
  );
}

const styles = StyleSheet.create({
  content: { gap: 18, padding: 20, paddingBottom: 48 },
  title: { color: "#17201c", fontSize: 28, fontWeight: "700" },
  body: { color: "#46534d", fontSize: 16, lineHeight: 23 },
  hint: { color: "#4d5a54", fontSize: 14, lineHeight: 20 },
  section: {
    backgroundColor: "#edf2ee",
    borderRadius: 14,
    gap: 12,
    padding: 16,
  },
  notice: {
    backgroundColor: "#fff",
    borderColor: "#c9d7cd",
    borderRadius: 14,
    borderWidth: 1,
    gap: 10,
    padding: 16,
  },
  statusCard: {
    backgroundColor: "#fff4db",
    borderRadius: 14,
    gap: 8,
    padding: 16,
  },
  readyCard: { backgroundColor: "#dcefe4" },
  errorCard: {
    backgroundColor: "#fff",
    borderColor: "#9b1c1c",
    borderRadius: 14,
    borderWidth: 1,
    gap: 10,
    padding: 16,
  },
  errorText: { color: "#9b1c1c", fontSize: 15, lineHeight: 22 },
  sectionTitle: { color: "#203a2e", fontSize: 19, fontWeight: "700" },
  switchRow: {
    alignItems: "center",
    borderBottomColor: "#d2ddd5",
    borderBottomWidth: 1,
    flexDirection: "row",
    gap: 12,
    justifyContent: "space-between",
    minHeight: 54,
  },
  switchLabel: { color: "#24342b", flex: 1, fontSize: 16 },
  fieldLabel: { color: "#203a2e", fontSize: 16, fontWeight: "700" },
  input: {
    backgroundColor: "#fff",
    borderColor: "#68786f",
    borderRadius: 10,
    borderWidth: 1,
    color: "#17201c",
    fontSize: 16,
    minHeight: 52,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  multiline: { minHeight: 110, textAlignVertical: "top" },
  choiceRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  choice: {
    alignItems: "center",
    backgroundColor: "#fff",
    borderColor: "#68786f",
    borderRadius: 22,
    borderWidth: 1,
    justifyContent: "center",
    minHeight: 44,
    paddingHorizontal: 14,
  },
  choiceSelected: {
    backgroundColor: "#dcefe4",
    borderColor: "#245d3a",
    borderWidth: 2,
  },
  choiceText: { color: "#24342b", fontSize: 14, fontWeight: "600" },
  choiceTextSelected: { color: "#17492b" },
  button: {
    alignItems: "center",
    backgroundColor: "#245d3a",
    borderRadius: 12,
    justifyContent: "center",
    minHeight: 50,
    paddingHorizontal: 18,
  },
  buttonText: { color: "#fff", fontSize: 16, fontWeight: "700" },
  disabled: { opacity: 0.55 },
  entry: {
    backgroundColor: "#fff",
    borderColor: "#d2ddd5",
    borderRadius: 12,
    borderWidth: 1,
    gap: 7,
    padding: 12,
  },
  summaryCard: {
    backgroundColor: "#fff",
    borderColor: "#d2ddd5",
    borderRadius: 12,
    borderWidth: 1,
    gap: 7,
    padding: 12,
  },
  summaryText: { color: "#24342b", fontSize: 14, lineHeight: 20 },
  entryTitle: { color: "#17201c", fontSize: 16, fontWeight: "700" },
  payload: { color: "#24342b", fontSize: 14, lineHeight: 20 },
  warning: { color: "#755006", fontSize: 14, lineHeight: 20 },
  linkRow: { flexDirection: "row", flexWrap: "wrap", gap: 16 },
  textLink: {
    color: "#245d3a",
    fontSize: 15,
    fontWeight: "700",
    paddingVertical: 8,
  },
});
