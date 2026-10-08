import { Pressable, Text, View } from "react-native";
import type { components } from "@personal-health/api-client";

import { ActionButton } from "../../profile/components/Ui";
import type { EvidenceLink } from "./AnalyticsSections";
import { styles } from "./insightsStyles";

type Insight = components["schemas"]["InsightResponse"];
type Recommendation = components["schemas"]["RecommendationResponse"];

export function InsightHistorySection({
  insights,
  cursor,
  expandedEvidence,
  busy,
  canGenerate,
  onGenerate,
  onToggleEvidence,
  onOpenEvidence,
  onDismiss,
  onLoadMore,
}: {
  insights: Insight[];
  cursor: string | null;
  expandedEvidence: Record<string, boolean>;
  busy: boolean;
  canGenerate: boolean;
  onGenerate: () => void;
  onToggleEvidence: (key: string) => void;
  onOpenEvidence: (reference: EvidenceLink) => void;
  onDismiss: (item: Insight) => void;
  onLoadMore: () => void;
}) {
  return (
    <View style={styles.section}>
      <Text accessibilityRole="header" style={styles.sectionTitle}>
        Evidence-linked insights
      </Text>
      <ActionButton
        label="Generate for this window"
        busy={busy}
        disabled={!canGenerate}
        onPress={onGenerate}
      />
      {insights.length === 0 ? (
        <Text style={styles.help}>
          No saved insights yet. Sparse data may have no eligible insight.
        </Text>
      ) : null}
      {insights.map((item) => (
        <View key={item.id} style={styles.card}>
          <Text style={styles.cardTitle}>{item.title}</Text>
          <Text style={styles.cardBody}>{item.insight.explanation}</Text>
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
                onPress={() => onOpenEvidence(reference)}
                style={styles.evidenceLink}
              >
                <Text style={styles.evidenceText}>
                  {reference.object_type} · revision {reference.revision} ·{" "}
                  {reference.object_id}
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
              onPress={() => onToggleEvidence(item.id)}
            />
          ) : null}
          {item.state === "current" ? (
            <ActionButton
              label="Dismiss insight"
              secondary
              busy={busy}
              onPress={() => onDismiss(item)}
            />
          ) : null}
        </View>
      ))}
      {cursor ? (
        <ActionButton
          label="Load more insight history"
          secondary
          busy={busy}
          onPress={onLoadMore}
        />
      ) : null}
    </View>
  );
}

export function RecommendationHistorySection({
  recommendations,
  cursor,
  busy,
  onChangeState,
  onLoadMore,
}: {
  recommendations: Recommendation[];
  cursor: string | null;
  busy: boolean;
  onChangeState: (
    item: Recommendation,
    state: "accepted" | "dismissed",
  ) => void;
  onLoadMore: () => void;
}) {
  return (
    <View style={styles.section}>
      <Text accessibilityRole="header" style={styles.sectionTitle}>
        Low-risk tracking suggestions
      </Text>
      {recommendations.length === 0 ? (
        <Text style={styles.help}>No current tracking suggestions.</Text>
      ) : null}
      {recommendations.map((item) => (
        <View key={item.id} style={styles.card}>
          <Text style={styles.cardTitle}>{item.title}</Text>
          <Text style={styles.cardBody}>{item.recommendation.suggestion}</Text>
          <Text style={styles.help}>
            {item.recommendation.rationale} · expires{" "}
            {new Date(item.recommendation.expires_at).toLocaleDateString()}
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
                onPress={() => onChangeState(item, "accepted")}
              />
              <ActionButton
                label="Dismiss"
                secondary
                busy={busy}
                onPress={() => onChangeState(item, "dismissed")}
              />
            </View>
          ) : (
            <Text style={styles.help}>
              State: {item.state}. Accepting records interest only; it does not
              change health data.
            </Text>
          )}
        </View>
      ))}
      {cursor ? (
        <ActionButton
          label="Load more recommendation history"
          secondary
          busy={busy}
          onPress={onLoadMore}
        />
      ) : null}
    </View>
  );
}
