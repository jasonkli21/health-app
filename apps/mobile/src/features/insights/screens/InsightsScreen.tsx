import { useRouter } from "expo-router";
import { SafeAreaView, ScrollView, Text, View } from "react-native";

import { LoadingMessage, StatusMessage } from "../../profile/components/Ui";
import {
  AssociationSection,
  MetricWindowSection,
  TrendResultSection,
} from "../components/AnalyticsSections";
import type { EvidenceLink } from "../components/AnalyticsSections";
import { ExperimentsSection } from "../components/ExperimentsSection";
import {
  InsightHistorySection,
  RecommendationHistorySection,
} from "../components/HistorySections";
import { styles } from "../components/insightsStyles";
import { evidenceDestination } from "../state";
import { useInsightsController } from "../useInsightsController";

export default function InsightsScreen() {
  const router = useRouter();
  const state = useInsightsController();

  function openEvidence(reference: EvidenceLink) {
    router.push(evidenceDestination(reference));
  }

  function toggleEvidence(key: string) {
    state.setExpandedEvidence((current) => ({
      ...current,
      [key]: !current[key],
    }));
  }

  function togglePair(pairId: string) {
    state.setAssociations([]);
    state.setSelectedPairs((current) =>
      current.includes(pairId)
        ? current.filter((value) => value !== pairId)
        : current.length < 5
          ? [...current, pairId]
          : current,
    );
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <Text accessibilityRole="header" style={styles.title}>
            Insights
          </Text>
          <Text style={styles.body}>
            Descriptive summaries of values you logged. Missing days stay
            visible as gaps; these results do not establish clinical meaning or
            cause.
          </Text>
        </View>

        {state.error ? (
          <StatusMessage
            title="Analytics request"
            message={state.error}
            tone="error"
          />
        ) : null}
        {state.loading ? <LoadingMessage label="Loading Insights" /> : null}

        {!state.loading ? (
          <>
            <MetricWindowSection
              metrics={state.metrics}
              metric={state.metric}
              from={state.from}
              to={state.to}
              timezone={state.timezone}
              busy={state.busy}
              onMetric={(metric) => {
                state.setMetric(metric);
                state.setTrend(null);
                state.setAssociations([]);
              }}
              onFrom={(from) => {
                state.setFrom(from);
                state.setTrend(null);
                state.setAssociations([]);
              }}
              onTo={(to) => {
                state.setTo(to);
                state.setTrend(null);
                state.setAssociations([]);
              }}
              onTimezone={(timezone) => {
                state.setTimezone(timezone);
                state.setTrend(null);
                state.setAssociations([]);
                state.setResults({});
              }}
              onShowTrend={() => void state.runTrend()}
            />

            <TrendResultSection
              trend={state.trend}
              expanded={state.expandedEvidence.trend ?? false}
              onToggleEvidence={() => toggleEvidence("trend")}
              onOpenEvidence={openEvidence}
            />

            <AssociationSection
              pairs={state.pairs}
              selectedPairs={state.selectedPairs}
              associations={state.associations}
              busy={state.busy}
              onTogglePair={togglePair}
              onAnalyze={() => void state.runAssociations()}
            />

            <InsightHistorySection
              insights={state.insights}
              cursor={state.insightCursor}
              expandedEvidence={state.expandedEvidence}
              busy={state.busy}
              canGenerate={Boolean(state.metric || state.selectedPairs.length)}
              onGenerate={() => void state.generateInsights()}
              onToggleEvidence={toggleEvidence}
              onOpenEvidence={openEvidence}
              onDismiss={(item) => void state.changeInsight(item)}
              onLoadMore={() => void state.loadMoreInsights()}
            />

            <RecommendationHistorySection
              recommendations={state.recommendations}
              cursor={state.recommendationCursor}
              busy={state.busy}
              onChangeState={(item, nextState) =>
                void state.changeRecommendation(item, nextState)
              }
              onLoadMore={() => void state.loadMoreRecommendations()}
            />

            <ExperimentsSection
              metrics={state.metrics}
              form={state.form}
              editing={state.editing}
              pendingCreate={state.pendingCreate !== null}
              experiments={state.experiments}
              results={state.results}
              cursor={state.experimentCursor}
              busy={state.busy}
              onFormChange={state.setForm}
              onSave={() => void state.saveExperiment()}
              onCancel={state.cancelExperimentEdit}
              onDiscardPending={() => state.setPendingCreate(null)}
              onEdit={state.editExperiment}
              onTransition={(item, nextState) =>
                void state.transitionExperiment(item, nextState)
              }
              onLoadResult={(item) => void state.loadExperimentResult(item)}
              onLoadMore={() => void state.loadMoreExperiments()}
            />
          </>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}
