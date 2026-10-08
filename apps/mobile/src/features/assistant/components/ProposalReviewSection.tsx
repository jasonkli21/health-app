import { ActivityIndicator, Text, View } from "react-native";
import type { components } from "@personal-health/api-client";

import { Button, Choice, ErrorMessage } from "./AssistantControls";
import { ProposalEditor } from "./ProposalEditor";
import type { ProposalEditorBaseline } from "./ProposalEditor";
import { styles } from "./assistantStyles";

type Summary = components["schemas"]["ProposalSummary"];
type Proposal = components["schemas"]["ProposalState"];
export type ProposalStateFilter =
  | "pending"
  | "applied"
  | "rejected"
  | "expired"
  | "superseded";

function readablePayload(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function commandTitle(action: string): string {
  return action
    .split(".")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" · ");
}

export function ProposalReviewSection({
  proposals,
  details,
  loading,
  error,
  actionId,
  editingProposalId,
  editingBaseline,
  rationaleDraft,
  commandDraft,
  evidenceDraft,
  filter,
  hasMore,
  onFilter,
  onReviewDetail,
  onEdit,
  onConfirm,
  onReject,
  onSaveEdit,
  onCancelEdit,
  onReplaceDraft,
  onRationaleChange,
  onCommandsChange,
  onEvidenceChange,
  onRefresh,
  onLoadMore,
}: {
  proposals: Summary[];
  details: Record<string, Proposal>;
  loading: boolean;
  error: string | null;
  actionId: string | null;
  editingProposalId: string | null;
  editingBaseline: ProposalEditorBaseline | null;
  rationaleDraft: string;
  commandDraft: string;
  evidenceDraft: string;
  filter: ProposalStateFilter;
  hasMore: boolean;
  onFilter: (filter: ProposalStateFilter) => void;
  onReviewDetail: (proposalId: string) => void;
  onEdit: (proposal: Proposal) => void;
  onConfirm: (proposal: Proposal) => void;
  onReject: (proposal: Proposal) => void;
  onSaveEdit: (proposal: Proposal) => void;
  onCancelEdit: () => void;
  onReplaceDraft: (proposal: Proposal) => void;
  onRationaleChange: (value: string) => void;
  onCommandsChange: (value: string) => void;
  onEvidenceChange: (value: string) => void;
  onRefresh: () => void;
  onLoadMore: () => void;
}) {
  return (
    <View style={styles.section}>
      <Text accessibilityRole="header" style={styles.sectionTitle}>
        Action proposals
      </Text>
      <Text style={styles.hint}>
        Review each typed change, evidence revision, source, and expiry. A
        deliberate Confirm and save action applies the displayed revision once.
        Editing creates a new revision and requires a fresh review.
      </Text>
      {error ? <ErrorMessage message={error} /> : null}
      <View style={styles.choiceRow}>
        {(
          ["pending", "applied", "rejected", "expired", "superseded"] as const
        ).map((state) => (
          <Choice
            key={state}
            label={state}
            selected={filter === state}
            onPress={() => onFilter(state)}
          />
        ))}
      </View>
      {loading ? (
        <ActivityIndicator accessibilityLabel="Loading action proposals" />
      ) : null}
      {!loading && !error && proposals.length === 0 ? (
        <Text style={styles.hint}>There are no recent action proposals.</Text>
      ) : null}
      {proposals.map((summary) => {
        const proposal = details[summary.id];
        if (
          !proposal ||
          proposal.revision !== summary.revision ||
          proposal.state !== summary.state
        ) {
          return (
            <View key={summary.id} style={styles.entry}>
              <Text style={styles.entryTitle}>
                {summary.state === "pending"
                  ? "Review proposal"
                  : `Proposal ${summary.state}`}
              </Text>
              <Text style={styles.hint}>
                {summary.origin === "ai" ? "AI suggested" : "Owner submitted"} ·{" "}
                revision {summary.revision} · expires {summary.expires_at}
              </Text>
              {summary.rationale ? (
                <Text style={styles.body}>{summary.rationale}</Text>
              ) : null}
              <Button
                label={
                  actionId === summary.id
                    ? "Loading…"
                    : "Review current proposal revision"
                }
                disabled={actionId !== null}
                onPress={() => onReviewDetail(summary.id)}
              />
            </View>
          );
        }
        return (
          <View key={proposal.id} style={styles.entry}>
            <Text style={styles.entryTitle}>
              {proposal.state === "pending"
                ? "Review proposal"
                : `Proposal ${proposal.state}`}
            </Text>
            <Text style={styles.hint}>
              {proposal.origin === "ai" ? "AI suggested" : "Owner submitted"} ·{" "}
              revision {proposal.revision} · expires {proposal.expires_at}
            </Text>
            {proposal.rationale ? (
              <Text style={styles.body}>{proposal.rationale}</Text>
            ) : null}
            {proposal.last_validation_summary?.valid === false ? (
              <View style={styles.errorCard}>
                <Text
                  accessibilityRole="alert"
                  accessibilityLiveRegion="polite"
                  style={styles.errorText}
                >
                  This proposal needs review because a referenced record
                  changed. The draft and prior confirmation are preserved.
                </Text>
                <Text selectable style={styles.payload}>
                  {readablePayload(
                    proposal.last_validation_summary.changed_references,
                  )}
                </Text>
              </View>
            ) : null}
            {proposal.evidence_refs.length ? (
              <View style={styles.evidenceList}>
                <Text style={styles.fieldLabel}>Evidence</Text>
                {proposal.evidence_refs.map((evidence) => (
                  <Text
                    key={`${evidence.object_id}:${evidence.revision}`}
                    style={styles.hint}
                  >
                    {evidence.title} · {evidence.object_type} · revision{" "}
                    {evidence.revision}
                  </Text>
                ))}
              </View>
            ) : (
              <Text style={styles.hint}>
                No supporting evidence references.
              </Text>
            )}
            {proposal.commands.map((command, index) => (
              <View
                key={`${proposal.id}:${index}`}
                style={styles.proposalCommand}
              >
                <Text style={styles.fieldLabel}>
                  Change {index + 1} · {commandTitle(command.action)}
                </Text>
                {"object_id" in command ? (
                  <Text style={styles.hint}>
                    Target {command.object_id} · based on revision{" "}
                    {command.expected_revision}
                  </Text>
                ) : null}
                {"id" in command ? (
                  <Text style={styles.hint}>New target ID · {command.id}</Text>
                ) : null}
                <Text selectable style={styles.payload}>
                  {readablePayload(command)}
                </Text>
              </View>
            ))}
            {(proposal.changes ?? []).map((change, index) => (
              <View
                key={`${proposal.id}:change:${index}`}
                style={styles.evidenceList}
              >
                <Text style={styles.fieldLabel}>
                  Before and after · {change.title}
                </Text>
                <Text style={styles.hint}>
                  Target {change.object_id} · reviewed revision{" "}
                  {change.revision}
                </Text>
                <Text selectable style={styles.payload}>
                  Before: {readablePayload(change.before)}
                </Text>
                <Text selectable style={styles.payload}>
                  After: {readablePayload(change.after)}
                </Text>
                {change.cleared_fields?.length ? (
                  <Text style={styles.hint}>
                    Fields cleared: {change.cleared_fields.join(", ")}
                  </Text>
                ) : null}
                {change.preserved_fields?.length ? (
                  <Text style={styles.hint}>
                    Fields preserved: {change.preserved_fields.join(", ")}
                  </Text>
                ) : null}
                {change.removed_plan_items?.length ? (
                  <Text style={styles.hint}>
                    Removed plan items:{" "}
                    {readablePayload(change.removed_plan_items)} ·{" "}
                    {change.schedules_to_retire} active schedules will be
                    retired.
                  </Text>
                ) : null}
              </View>
            ))}
            {proposal.state === "applied" &&
            proposal.results &&
            proposal.results.length > 0 ? (
              <View style={styles.evidenceList}>
                <Text style={styles.fieldLabel}>Saved results</Text>
                {proposal.results.map((result) => (
                  <Text
                    key={`${result.object_id}:${result.revision}`}
                    style={styles.hint}
                  >
                    {result.object_type} · revision {result.revision} ·{" "}
                    {result.object_id}
                  </Text>
                ))}
              </View>
            ) : null}
            {proposal.state === "pending" ? (
              editingProposalId === proposal.id ? (
                <ProposalEditor
                  proposalId={proposal.id}
                  proposalRevision={proposal.revision}
                  baseline={editingBaseline}
                  rationale={rationaleDraft}
                  commands={commandDraft}
                  evidence={evidenceDraft}
                  saving={actionId !== null}
                  onRationaleChange={onRationaleChange}
                  onCommandsChange={onCommandsChange}
                  onEvidenceChange={onEvidenceChange}
                  onSave={() => onSaveEdit(proposal)}
                  onCancel={onCancelEdit}
                  onReplaceDraft={() => onReplaceDraft(proposal)}
                />
              ) : (
                <View style={styles.proposalActions}>
                  <Button
                    label="Edit proposal"
                    disabled={actionId !== null}
                    onPress={() => onEdit(proposal)}
                  />
                  <Button
                    label={
                      actionId === proposal.id ? "Saving…" : "Confirm and save"
                    }
                    disabled={actionId !== null}
                    onPress={() => onConfirm(proposal)}
                  />
                  <Button
                    label="Reject proposal"
                    disabled={actionId !== null}
                    onPress={() => onReject(proposal)}
                  />
                </View>
              )
            ) : null}
          </View>
        );
      })}
      {!loading ? (
        <Button
          label="Refresh proposals"
          disabled={actionId !== null}
          onPress={onRefresh}
        />
      ) : null}
      {!loading && hasMore ? (
        <Button
          label="Load more proposals"
          disabled={loading}
          onPress={onLoadMore}
        />
      ) : null}
    </View>
  );
}
