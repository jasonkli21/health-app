import { ActivityIndicator, ScrollView, Text, View } from "react-native";
import { Link } from "expo-router";

import {
  AssistantMessageSection,
  AssistantSearchSection,
  ContextPreviewSection,
  ContextScopeSection,
} from "../components/AssistantContextSections";
import { Button } from "../components/AssistantControls";
import { ProposalReviewSection } from "../components/ProposalReviewSection";
import { styles } from "../components/assistantStyles";
import { useAssistantController } from "../useAssistantController";
import type { ProposalStateFilter } from "../components/ProposalReviewSection";

export default function AssistantScreen() {
  const assistant = useAssistantController();

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <Text accessibilityRole="header" style={styles.title}>
        Assistant
      </Text>
      <Text style={styles.body}>
        Review the exact Health items selected for a future read-only Assistant
        request. Assistant messages cannot save directly. Supported typed
        proposals require a deliberate review and confirmation before they can
        change health records.
      </Text>

      {assistant.status ? (
        <View
          style={[
            styles.statusCard,
            assistant.status.enabled && styles.readyCard,
          ]}
        >
          <Text accessibilityRole="header" style={styles.sectionTitle}>
            {assistant.status.enabled
              ? "Assistant available"
              : "Assistant unavailable"}
          </Text>
          <Text style={styles.body}>{assistant.status.message}</Text>
        </View>
      ) : assistant.statusError ? (
        <View style={styles.errorCard}>
          <Text accessibilityRole="alert" style={styles.errorText}>
            {assistant.statusError}
          </Text>
          <AssistantRetryStatus onRetry={() => void assistant.loadStatus()} />
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

      <ProposalReviewSection
        proposals={assistant.proposals}
        details={assistant.proposalDetails}
        loading={assistant.proposalsLoading}
        error={assistant.proposalError}
        actionId={assistant.proposalActionId}
        editingProposalId={assistant.editingProposalId}
        editingBaseline={assistant.editingBaseline}
        rationaleDraft={assistant.proposalRationaleDraft}
        commandDraft={assistant.proposalCommandDraft}
        evidenceDraft={assistant.proposalEvidenceDraft}
        filter={assistant.proposalStateFilter}
        hasMore={assistant.proposalHasMore}
        onFilter={(filter: ProposalStateFilter) =>
          assistant.setProposalStateFilter(filter)
        }
        onReviewDetail={(proposalId) =>
          void assistant.loadProposalDetail(proposalId)
        }
        onEdit={assistant.beginEdit}
        onConfirm={(proposal) => void assistant.confirmProposal(proposal)}
        onReject={(proposal) => void assistant.rejectProposal(proposal)}
        onSaveEdit={(proposal) => void assistant.saveProposalEdit(proposal)}
        onCancelEdit={assistant.cancelProposalEdit}
        onReplaceDraft={assistant.beginEdit}
        onRationaleChange={assistant.changeProposalRationale}
        onCommandsChange={assistant.changeProposalCommands}
        onEvidenceChange={assistant.changeProposalEvidence}
        onRefresh={assistant.refreshProposals}
        onLoadMore={() => void assistant.loadProposals(true)}
      />

      <ContextScopeSection
        resourceTypes={assistant.resourceTypes}
        domains={assistant.domains}
        task={assistant.task}
        taskKind={assistant.taskKind}
        lookbackDays={assistant.lookbackDays}
        busy={assistant.busy}
        onResourceType={assistant.toggleResourceType}
        onToggleDomain={(domain) =>
          assistant.setDomains((current) =>
            current.includes(domain)
              ? current.filter((value) => value !== domain)
              : [...current, domain],
          )
        }
        onTask={assistant.setTask}
        onTaskKind={assistant.setTaskKind}
        onLookbackDays={assistant.setLookbackDays}
        onPreview={() => void assistant.previewContext()}
      />

      <ContextPreviewSection
        pack={assistant.pack}
        previewIsCurrent={assistant.previewIsCurrent}
        error={assistant.previewError}
        excludedObjectIds={assistant.excludedObjectIds}
        onToggleExcluded={(objectId) =>
          assistant.setExcludedObjectIds((current) =>
            current.includes(objectId)
              ? current.filter((id) => id !== objectId)
              : [...current, objectId].slice(0, 100),
          )
        }
      />

      <AssistantSearchSection
        searchText={assistant.searchText}
        currentSearchKey={assistant.currentSearchKey}
        error={assistant.searchError}
        errorKey={assistant.searchErrorKey}
        stale={assistant.searchStale}
        results={assistant.visibleSearchResults}
        cursor={assistant.visibleSearchCursor}
        busy={assistant.busy}
        resourceTypeCount={assistant.resourceTypes.length}
        onSearchText={assistant.changeSearchText}
        onSearch={(append) => void assistant.search(append)}
      />

      <AssistantMessageSection
        status={assistant.status}
        message={assistant.message}
        resourceTypeCount={assistant.resourceTypes.length}
        busy={assistant.busy}
        reply={assistant.reply}
        onMessage={assistant.setMessage}
        onSend={() => void assistant.sendMessage()}
      />
    </ScrollView>
  );
}

function AssistantRetryStatus({ onRetry }: { onRetry: () => void }) {
  return <Button label="Retry status" onPress={onRetry} />;
}
