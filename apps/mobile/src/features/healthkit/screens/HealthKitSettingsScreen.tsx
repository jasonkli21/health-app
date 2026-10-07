import type { components } from "@personal-health/api-client";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { sessionStore } from "../../../auth/sessionStore";
import { HealthKitConsentStore } from "../../../integrations/healthkit/consent";
import { getHealthKitNativeCapability } from "../../../integrations/healthkit/nativeAdapter";
import type { HealthKitResourceType } from "../../../integrations/healthkit/types";
import { healthkitApi, healthkitErrorMessage } from "../api";

type Status = components["schemas"]["HealthKitImportStatusResponse"];
type ResourceStatus = components["schemas"]["HealthKitImportTypeStatus"];

const consentStore = new HealthKitConsentStore();
const labels: Record<HealthKitResourceType, string> = {
  workouts: "Workouts",
  sleep: "Sleep intervals",
  steps: "Daily steps",
  weight: "Weight",
  resting_heart_rate: "Resting heart rate",
  heart_rate_summary: "Daily heart-rate summary",
};
const resources = Object.keys(labels) as HealthKitResourceType[];

function currentOwnerScope(): string {
  return sessionStore.getSnapshot().userId ?? "local-development-owner";
}

export function HealthKitSettingsScreen() {
  const ownerId = currentOwnerScope();
  const capability = getHealthKitNativeCapability(
    Platform.OS === "ios"
      ? "ios"
      : Platform.OS === "android"
        ? "android"
        : "web",
  );
  const [status, setStatus] = useState<Status | null>(null);
  const [consent, setConsent] = useState<
    Partial<Record<HealthKitResourceType, boolean>>
  >({});
  const [lookback, setLookback] = useState(30);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const refreshStatus = useCallback(async () => {
    try {
      const next = await healthkitApi.getHealthKitImportStatus();
      setStatus(next);
      setError(null);
      return true;
    } catch {
      setError(healthkitErrorMessage());
      return false;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      let secureSettingsUnavailable = false;
      try {
        const [lookbackDays, enabledByType] = await Promise.all([
          consentStore.getLookbackDays(ownerId),
          Promise.all(
            resources.map((item) => consentStore.isEnabled(ownerId, item)),
          ),
        ]);
        if (cancelled) return;
        setLookback(lookbackDays);
        setConsent(
          Object.fromEntries(
            resources.map((item, index) => [item, enabledByType[index]]),
          ),
        );
      } catch {
        secureSettingsUnavailable = true;
      }
      if (cancelled) return;
      const serverStatusLoaded = await refreshStatus();
      if (!cancelled && secureSettingsUnavailable && serverStatusLoaded) {
        setError(
          "Secure HealthKit settings could not be loaded on this device.",
        );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [ownerId, refreshStatus]);

  const statusByType = useMemo(
    () =>
      new Map(status?.types.map((item) => [item.resource_type, item]) ?? []),
    [status],
  );

  async function changeConsent(
    resourceType: HealthKitResourceType,
    enabled: boolean,
  ) {
    setSaving(true);
    try {
      await consentStore.setEnabled(ownerId, resourceType, enabled);
      setConsent((current) => ({ ...current, [resourceType]: enabled }));
      setError(null);
    } catch {
      setError("The HealthKit consent choice could not be saved securely.");
    } finally {
      setSaving(false);
    }
  }

  async function changeLookback(next: number) {
    const bounded = Math.max(1, Math.min(90, next));
    setSaving(true);
    try {
      await consentStore.setLookbackDays(ownerId, bounded);
      setLookback(bounded);
      setError(null);
    } catch {
      setError("The initial import lookback could not be saved securely.");
    } finally {
      setSaving(false);
    }
  }

  async function preferSource(
    resourceType: "steps" | "heart_rate_summary",
    installationId: string,
    resourceStatus: ResourceStatus,
  ) {
    setSaving(true);
    try {
      await healthkitApi.setHealthKitSourcePreference({
        resource_type: resourceType,
        device_installation_id: installationId,
        ...(resourceStatus.preference_revision === null
          ? {}
          : { expected_revision: resourceStatus.preference_revision }),
      });
      await refreshStatus();
      setError(null);
    } catch {
      setError("The aggregate source preference could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text accessibilityRole="header" style={styles.title}>
          HealthKit
        </Text>
        <Text style={styles.body}>
          Choose the health types you may want to import. Each choice is stored
          for this app account. Turning a type off stops future reads and
          uploads; existing imported records remain in your Health history.
        </Text>

        <View style={styles.notice}>
          <Text accessibilityRole="header" style={styles.noticeTitle}>
            {capability.status === "native_adapter_unavailable"
              ? "Native HealthKit adapter unavailable"
              : "HealthKit is unsupported on this device"}
          </Text>
          <Text style={styles.body}>
            A compatible iOS development build and verified native adapter are
            not installed. Consent choices below do not request Apple
            permissions or start a sync.
          </Text>
        </View>

        <View style={styles.lookback}>
          <Text style={styles.sectionTitle}>Initial lookback</Text>
          <Text style={styles.body}>{lookback} days (maximum 90)</Text>
          <View style={styles.row}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Decrease initial lookback"
              disabled={saving || lookback <= 1}
              onPress={() => void changeLookback(lookback - 1)}
              style={styles.stepper}
            >
              <Text style={styles.stepperLabel}>−</Text>
            </Pressable>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Increase initial lookback"
              disabled={saving || lookback >= 90}
              onPress={() => void changeLookback(lookback + 1)}
              style={styles.stepper}
            >
              <Text style={styles.stepperLabel}>+</Text>
            </Pressable>
          </View>
        </View>

        <Text accessibilityRole="header" style={styles.sectionTitle}>
          Import types
        </Text>
        {resources.map((resourceType) => {
          const resourceStatus = statusByType.get(resourceType);
          return (
            <View key={resourceType} style={styles.card}>
              <View style={styles.row}>
                <View style={styles.typeCopy}>
                  <Text style={styles.typeTitle}>{labels[resourceType]}</Text>
                  <Text style={styles.body}>
                    {resourceStatus
                      ? `${resourceStatus.imported_count} imported · ${resourceStatus.tombstoned_count} removed`
                      : "Import status unavailable"}
                  </Text>
                </View>
                <Switch
                  accessibilityLabel={`Allow ${labels[resourceType]} import`}
                  disabled={saving}
                  value={consent[resourceType] ?? false}
                  onValueChange={(enabled) =>
                    void changeConsent(resourceType, enabled)
                  }
                />
              </View>
              {resourceStatus?.last_success_at ? (
                <Text style={styles.caption}>
                  Last successful sync: {resourceStatus.last_success_at}
                </Text>
              ) : (
                <Text style={styles.caption}>No successful sync yet</Text>
              )}
              {resourceStatus &&
              (resourceType === "steps" ||
                resourceType === "heart_rate_summary") &&
              status?.installations.length ? (
                <View style={styles.preferenceGroup}>
                  <Text style={styles.caption}>Preferred aggregate source</Text>
                  {status.installations.map((installation) => (
                    <Pressable
                      key={installation.device_installation_id}
                      accessibilityRole="button"
                      disabled={saving}
                      onPress={() =>
                        void preferSource(
                          resourceType,
                          installation.device_installation_id,
                          resourceStatus,
                        )
                      }
                    >
                      <Text
                        style={
                          resourceStatus?.preferred_installation_id ===
                          installation.device_installation_id
                            ? styles.selectedPreference
                            : styles.preference
                        }
                      >
                        {installation.source_name}
                        {resourceStatus?.preferred_installation_id ===
                        installation.device_installation_id
                          ? " · selected"
                          : ""}
                      </Text>
                    </Pressable>
                  ))}
                </View>
              ) : null}
            </View>
          );
        })}

        {error ? (
          <Text accessibilityRole="alert" style={styles.error}>
            {error}
          </Text>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { backgroundColor: "#f7f9f7", flex: 1 },
  content: { gap: 16, padding: 20 },
  title: { color: "#17201c", fontSize: 28, fontWeight: "700" },
  sectionTitle: { color: "#24342b", fontSize: 18, fontWeight: "700" },
  body: { color: "#46534d", fontSize: 14, lineHeight: 20 },
  notice: {
    backgroundColor: "#fff4dc",
    borderColor: "#94713b",
    borderRadius: 12,
    borderWidth: 1,
    gap: 6,
    padding: 14,
  },
  noticeTitle: { color: "#443416", fontSize: 16, fontWeight: "700" },
  lookback: { backgroundColor: "#fff", borderRadius: 12, gap: 8, padding: 14 },
  card: { backgroundColor: "#fff", borderRadius: 12, gap: 8, padding: 14 },
  row: { alignItems: "center", flexDirection: "row", gap: 12 },
  typeCopy: { flex: 1, gap: 4 },
  typeTitle: { color: "#24342b", fontSize: 16, fontWeight: "600" },
  caption: { color: "#59675f", fontSize: 12 },
  stepper: {
    alignItems: "center",
    borderColor: "#52645a",
    borderRadius: 10,
    borderWidth: 1,
    height: 40,
    justifyContent: "center",
    width: 52,
  },
  stepperLabel: { color: "#24342b", fontSize: 22, fontWeight: "600" },
  preferenceGroup: {
    borderTopColor: "#e4eae5",
    borderTopWidth: 1,
    gap: 8,
    paddingTop: 8,
  },
  preference: { color: "#245d3a", fontSize: 14 },
  selectedPreference: { color: "#24342b", fontSize: 14, fontWeight: "700" },
  error: { color: "#9d2020", fontSize: 14 },
});
