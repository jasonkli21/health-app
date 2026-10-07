import { ApiError } from "@personal-health/api-client";
import { useCallback, useEffect, useState } from "react";
import * as SecureStore from "expo-secure-store";
import {
  Pressable,
  ScrollView,
  Share,
  StyleSheet,
  Text,
  TextInput,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { signOutCurrentUser } from "../../../auth/firebaseSession";
import { sessionStore } from "../../../auth/sessionStore";
import { accountDataApi, createDeletionRequestId } from "../api";
import { HealthKitConsentStore } from "../../../integrations/healthkit/consent";
import { SecureCheckpointStore } from "../../../integrations/healthkit/checkpoint";
import { secureKeySegment } from "../../../integrations/healthkit/secureKey";

const CONFIRMATION = "DELETE MY HEALTH DATA";
const consentStore = new HealthKitConsentStore();
const checkpointStore = new SecureCheckpointStore();

function pendingRequestKey(ownerId: string): string {
  return `account.delete.${secureKeySegment(ownerId)}.v1`;
}

function userFacingError(error: unknown, deletionRequest = false): string {
  if (error instanceof ApiError) {
    if (error.body?.code === "recent_authentication_required")
      return "Sign out and sign in again, then continue the same deletion request.";
    return (
      error.body?.message ?? "The account data request could not be completed."
    );
  }
  return deletionRequest
    ? "Could not reach your Health service. The request ID is saved so you can continue safely."
    : "Could not reach your Health service to prepare the export.";
}

export function AccountDataScreen() {
  const session = sessionStore.getSnapshot();
  const localScope = session.userId ?? "development-local";
  const requestKey = pendingRequestKey(localScope);
  const [confirmation, setConfirmation] = useState("");
  const [requestId, setRequestId] = useState<string | null>(null);
  const [deletionStatus, setDeletionStatus] = useState<
    "running" | "failed" | "completed" | null
  >(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const finishDeletion = useCallback(async (): Promise<void> => {
    if (session.userId) {
      await consentStore.clearOwner(session.userId);
      await checkpointStore.clearOwner(session.userId);
    }
    await SecureStore.deleteItemAsync(requestKey);
    setDeletionStatus("completed");
    setMessage("Health data deletion is complete. Signing out now.");
    await signOutCurrentUser();
  }, [requestKey, session.userId]);

  useEffect(() => {
    let active = true;
    void (async () => {
      const savedId = await SecureStore.getItemAsync(requestKey);
      if (!active || !savedId) return;
      setRequestId(savedId);
      try {
        const status = await accountDataApi.getOwnerDataDeletionStatus({
          request_id: savedId,
        });
        if (!active) return;
        setDeletionStatus(status.status);
        if (status.status === "completed") await finishDeletion();
        else setMessage("A saved deletion request is ready to continue.");
      } catch (error) {
        if (active) setMessage(userFacingError(error, true));
      }
    })();
    return () => {
      active = false;
    };
  }, [finishDeletion, requestKey]);

  async function exportData(): Promise<void> {
    setBusy(true);
    setMessage(null);
    try {
      const snapshot = await accountDataApi.exportCurrentOwnerData();
      await Share.share({
        title: "Personal Health data export",
        message: JSON.stringify(snapshot),
      });
      setMessage("Your data export is ready in the share sheet.");
    } catch (error) {
      setMessage(userFacingError(error));
    } finally {
      setBusy(false);
    }
  }

  async function continueDeletion(): Promise<void> {
    if (!requestId && confirmation !== CONFIRMATION) {
      setMessage(`Type ${CONFIRMATION} to confirm this irreversible action.`);
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const activeRequestId = requestId ?? createDeletionRequestId();
      if (!requestId) {
        await SecureStore.setItemAsync(requestKey, activeRequestId);
        setRequestId(activeRequestId);
      }
      const result = await accountDataApi.requestOwnerDataDeletion({
        request_id: activeRequestId,
        confirmation: CONFIRMATION,
      });
      setDeletionStatus(result.status);
      if (result.status === "completed") {
        await finishDeletion();
      } else {
        setMessage(
          result.status === "running"
            ? "Deletion is still running. Continue this request to process the next bounded cleanup step."
            : "Deletion did not finish. Continue this request to retry the failed cleanup step.",
        );
      }
    } catch (error) {
      setMessage(userFacingError(error, true));
    } finally {
      setBusy(false);
    }
  }

  return (
    <SafeAreaView style={styles.page}>
      <ScrollView
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
      >
        <Text accessibilityRole="header" style={styles.title}>
          Your data
        </Text>
        <Text style={styles.body}>
          Export a copy of your current Health service data, or request deletion
          of that data. Deletion also clears this account’s saved HealthKit
          consent and checkpoints. It does not delete your sign-in account,
          Apple Health data, or copies held by other services. You choose where
          the exported copy goes; the receiving app may retain it.
        </Text>
        <Pressable
          accessibilityRole="button"
          disabled={busy || deletionStatus === "completed"}
          onPress={() => void exportData()}
          style={styles.secondaryButton}
        >
          <Text style={styles.secondaryButtonText}>
            {busy ? "Working…" : "Export my data"}
          </Text>
        </Pressable>
        <Text accessibilityRole="header" style={styles.sectionTitle}>
          Delete Health service data
        </Text>
        <Text style={styles.body}>
          This cannot be undone. The service keeps a minimal account marker.
          Restoring an older backup could restore deleted data until a restore
          replay process is in place.
        </Text>
        {requestId ? (
          <Text accessibilityLiveRegion="polite">
            Request status: {deletionStatus ?? "checking"}
          </Text>
        ) : (
          <TextInput
            accessibilityLabel={`Type ${CONFIRMATION} to confirm deletion`}
            autoCapitalize="characters"
            autoCorrect={false}
            onChangeText={setConfirmation}
            placeholder={CONFIRMATION}
            value={confirmation}
            style={styles.input}
          />
        )}
        {message ? (
          <Text accessibilityRole="alert" style={styles.message}>
            {message}
          </Text>
        ) : null}
        <Pressable
          accessibilityRole="button"
          disabled={busy || deletionStatus === "completed"}
          onPress={() => void continueDeletion()}
          style={styles.deleteButton}
        >
          <Text style={styles.deleteButtonText}>
            {busy
              ? "Processing…"
              : requestId
                ? "Continue deletion"
                : "Delete my data"}
          </Text>
        </Pressable>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  page: { backgroundColor: "#f7f9f7", flex: 1 },
  content: { flex: 1, gap: 16, padding: 24 },
  title: { color: "#17201c", fontSize: 30, fontWeight: "700" },
  sectionTitle: { color: "#17201c", fontSize: 20, fontWeight: "700" },
  body: { color: "#46534d", fontSize: 16, lineHeight: 23 },
  input: {
    backgroundColor: "#fff",
    borderColor: "#52645a",
    borderRadius: 10,
    borderWidth: 1,
    padding: 14,
  },
  message: { color: "#46534d", fontSize: 15, lineHeight: 22 },
  secondaryButton: {
    alignSelf: "flex-start",
    backgroundColor: "#fff",
    borderColor: "#52645a",
    borderRadius: 10,
    borderWidth: 1,
    paddingHorizontal: 18,
    paddingVertical: 14,
  },
  secondaryButtonText: { color: "#24342b", fontSize: 16, fontWeight: "700" },
  deleteButton: {
    alignSelf: "flex-start",
    backgroundColor: "#8e1c1c",
    borderRadius: 10,
    paddingHorizontal: 18,
    paddingVertical: 14,
  },
  deleteButtonText: { color: "#fff", fontSize: 16, fontWeight: "700" },
});
