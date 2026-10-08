import { Pressable, Text, View } from "react-native";
import type { components } from "@personal-health/api-client";

import { ActionButton } from "../../profile/components/Ui";
import {
  formatInsightValue,
  SelectButton,
  ValueField,
} from "./InsightsControls";
import { styles } from "./insightsStyles";

type Metric = components["schemas"]["MetricDefinition"];
type Pair = components["schemas"]["AssociationPair"];
type Trend = components["schemas"]["StoredTrendResponse"];
type Association = components["schemas"]["StoredAssociationResponse"];
export type EvidenceLink =
  | components["schemas"]["InsightEvidenceReference"]
  | components["schemas"]["health_api__domain__analytics__EvidenceReference"];

export function MetricWindowSection({
  metrics,
  metric,
  from,
  to,
  timezone,
  busy,
  onMetric,
  onFrom,
  onTo,
  onTimezone,
  onShowTrend,
}: {
  metrics: Metric[];
  metric: string;
  from: string;
  to: string;
  timezone: string;
  busy: boolean;
  onMetric: (value: string) => void;
  onFrom: (value: string) => void;
  onTo: (value: string) => void;
  onTimezone: (value: string) => void;
  onShowTrend: () => void;
}) {
  const selectedMetric = metrics.find((item) => item.metric === metric);
  return (
    <View style={styles.section}>
      <Text accessibilityRole="header" style={styles.sectionTitle}>
        Choose a metric
      </Text>
      <Text style={styles.help}>
        Units and aggregation are shown for each supported metric. Tracker
        versions remain separate.
      </Text>
      <View style={styles.choices}>
        {metrics.map((item) => (
          <SelectButton
            key={item.metric}
            label={`${item.label} · ${item.unit}`}
            selected={metric === item.metric}
            onPress={() => onMetric(item.metric)}
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
          onChange={onFrom}
          placeholder="YYYY-MM-DD"
        />
        <ValueField
          label="To date"
          value={to}
          onChange={onTo}
          placeholder="YYYY-MM-DD"
        />
      </View>
      <ValueField
        label="IANA timezone"
        value={timezone}
        onChange={onTimezone}
        placeholder="America/Los_Angeles"
      />
      <ActionButton
        label="Show trend"
        busy={busy}
        disabled={!metric}
        onPress={onShowTrend}
      />
    </View>
  );
}

export function TrendResultSection({
  trend,
  expanded,
  onToggleEvidence,
  onOpenEvidence,
}: {
  trend: Trend | null;
  expanded: boolean;
  onToggleEvidence: () => void;
  onOpenEvidence: (reference: EvidenceLink) => void;
}) {
  if (!trend) return null;
  const visiblePoints = trend.result.points.slice(-14);
  return (
    <View style={styles.section}>
      <Text accessibilityRole="header" style={styles.sectionTitle}>
        {trend.result.label}
      </Text>
      <Text style={styles.help}>
        {trend.result.from_date}–{trend.result.to_date} ·{" "}
        {trend.result.timezone}
        {" · "}
        {trend.result.method_version}
      </Text>
      <Text style={styles.summary}>
        Mean {formatInsightValue(trend.result.mean, trend.result.unit)} · median{" "}
        {formatInsightValue(trend.result.median, trend.result.unit)}
      </Text>
      <Text style={styles.help}>
        Coverage: {trend.result.coverage.known_days}/
        {trend.result.coverage.calendar_days} known days;{" "}
        {trend.result.coverage.missing_days} missing;{" "}
        {trend.result.coverage.partial_days} partial. Seven-known-day rolling
        means: {trend.result.rolling_7_known_day_mean.length}.
      </Text>
      {trend.result.comparison ? (
        <Text style={styles.help}>
          Descriptive half-window means:{" "}
          {formatInsightValue(
            trend.result.comparison.before.mean,
            trend.result.unit,
          )}{" "}
          then{" "}
          {formatInsightValue(
            trend.result.comparison.after.mean,
            trend.result.unit,
          )}
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
            {formatInsightValue(point.value, trend.result.unit)}
          </Text>
          <Text style={styles.tableMeta}>
            {point.value === null
              ? "No known value"
              : `${point.known_count} known${point.partial ? " · partial" : ""}`}
          </Text>
        </View>
      ))}
      <Text style={styles.help}>
        {trend.result.evidence_refs.length} exact source revisions support this
        result.
      </Text>
      {trend.result.evidence_refs
        .slice(0, expanded ? undefined : 8)
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
      {trend.result.evidence_refs.length > 8 ? (
        <ActionButton
          label={
            expanded
              ? "Show fewer source references"
              : `Show all ${trend.result.evidence_refs.length} source references`
          }
          secondary
          onPress={onToggleEvidence}
        />
      ) : null}
    </View>
  );
}

export function AssociationSection({
  pairs,
  selectedPairs,
  associations,
  busy,
  onTogglePair,
  onAnalyze,
}: {
  pairs: Pair[];
  selectedPairs: string[];
  associations: Association[];
  busy: boolean;
  onTogglePair: (id: string) => void;
  onAnalyze: () => void;
}) {
  return (
    <View style={styles.section}>
      <Text accessibilityRole="header" style={styles.sectionTitle}>
        Same-day associations
      </Text>
      <Text style={styles.help}>
        Select up to five predefined pairs. Results require at least 14 paired
        days across 21 calendar days.
      </Text>
      <View style={styles.choices}>
        {pairs.map((pair) => (
          <SelectButton
            key={pair.id}
            label={`${pair.first.replaceAll("_", " ")} ↔ ${pair.second.replaceAll("_", " ")}`}
            selected={selectedPairs.includes(pair.id)}
            onPress={() => onTogglePair(pair.id)}
          />
        ))}
      </View>
      <ActionButton
        label="Analyze selected pairs"
        secondary
        busy={busy}
        disabled={!selectedPairs.length}
        onPress={onAnalyze}
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
  );
}
