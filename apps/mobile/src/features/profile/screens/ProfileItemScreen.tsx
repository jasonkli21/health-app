import { useCallback, useState } from "react";
import { Alert, ScrollView, StyleSheet, Text, View } from "react-native";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";

import { profileApi, profileErrorMessage } from "../api";
import { ProfileValueDisplay } from "../components/ProfileValueDisplay";
import { ActionButton, LoadingMessage, StatusMessage } from "../components/Ui";
import { formatInstant, type ProfileItem } from "../model";

function Definition({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.definition}>
      <Text style={styles.definitionLabel}>{label}</Text>
      <Text style={styles.definitionValue}>{value}</Text>
    </View>
  );
}

export default function ProfileItemScreen() {
  const { itemId } = useLocalSearchParams<{ itemId: string }>();
  const router = useRouter();
  const [item, setItem] = useState<ProfileItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const [archiving, setArchiving] = useState(false);

  useFocusEffect(
    useCallback(() => {
      let current = true;
      setLoading(true);
      setError(null);
      void profileApi
        .getProfileItem({ item_id: itemId })
        .then(
          (value) => {
            if (current) setItem(value);
          },
          (requestError: unknown) => {
            if (current) setError(profileErrorMessage(requestError));
          },
        )
        .finally(() => {
          if (current) setLoading(false);
        });
      return () => {
        current = false;
      };
      // Retry state intentionally recreates this focus callback to refetch server truth.
      // eslint-disable-next-line react-hooks/exhaustive-deps -- retry token is an effect trigger.
    }, [itemId, reload]),
  );

  function confirmArchive() {
    if (!item) return;
    Alert.alert(
      "Archive Profile item?",
      "It will be removed from your active Profile. Its history will remain available to you.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Archive",
          style: "destructive",
          onPress: () => void archive(),
        },
      ],
    );
  }

  async function archive() {
    if (!item) return;
    setArchiving(true);
    setError(null);
    try {
      const archived = await profileApi.archiveProfileItem(
        { item_id: item.id },
        { expected_revision: item.revision },
      );
      setItem(archived);
    } catch (requestError) {
      setError(profileErrorMessage(requestError));
    } finally {
      setArchiving(false);
    }
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      {loading ? <LoadingMessage label="Loading Profile item" /> : null}
      {error ? (
        <View style={styles.content}>
          <StatusMessage
            title="Profile request failed"
            message={error}
            tone="error"
          />
          <ActionButton
            label="Reload latest Profile item"
            onPress={() => setReload((value) => value + 1)}
          />
        </View>
      ) : null}
      {!loading && !error && item ? (
        <ScrollView contentContainerStyle={styles.content}>
          {item.status === "archived" ? (
            <StatusMessage
              title="Archived Profile item"
              message="This item is no longer part of your active Profile. Its past revisions remain available."
            />
          ) : null}
          <Text accessibilityRole="header" style={styles.title}>
            {item.profile.label}
          </Text>
          <Text style={styles.subtitle}>
            {item.profile.category[0]?.toUpperCase()}
            {item.profile.category.slice(1)} · {item.profile.kind}
          </Text>
          <ProfileValueDisplay value={item.profile.value} />
          {item.notes ? <Definition label="Notes" value={item.notes} /> : null}
          <Definition
            label="Effective start"
            value={formatInstant(item.valid_from)}
          />
          <Definition
            label="Effective end"
            value={formatInstant(item.valid_to)}
          />
          <Definition
            label="AI use permission"
            value={item.permissions.ai_use_allowed ? "Allowed" : "Not allowed"}
          />
          <Definition
            label="Use by other apps and health domains through Personal AI"
            value={
              item.permissions.cross_domain_use_allowed
                ? "Allowed"
                : "Not allowed"
            }
          />
          <Definition
            label="Source"
            value={`${item.source.name} (${item.source.kind})`}
          />
          <Definition label="Confirmation" value={item.confirmation_status} />
          <Definition label="Revision" value={`Revision ${item.revision}`} />
          <Definition
            label="Recorded"
            value={formatInstant(item.recorded_at)}
          />
          <View style={styles.actions}>
            {item.status === "active" ? (
              <>
                <ActionButton
                  label="Edit Profile item"
                  onPress={() =>
                    router.push({
                      pathname: "/profile/[itemId]/edit",
                      params: { itemId: item.id },
                    })
                  }
                />
                <ActionButton
                  label="Archive Profile item"
                  onPress={confirmArchive}
                  busy={archiving}
                  secondary
                />
              </>
            ) : null}
            <ActionButton
              label="View Profile history"
              onPress={() =>
                router.push({
                  pathname: "/profile/[itemId]/history",
                  params: { itemId: item.id },
                })
              }
              secondary
            />
          </View>
        </ScrollView>
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { backgroundColor: "#f7f9f7", flex: 1 },
  content: { gap: 16, padding: 20, paddingBottom: 36 },
  title: { color: "#17201c", fontSize: 28, fontWeight: "700" },
  subtitle: { color: "#46534d", fontSize: 16 },
  definition: {
    borderBottomColor: "#d2dbd5",
    borderBottomWidth: 1,
    gap: 4,
    paddingVertical: 12,
  },
  definitionLabel: { color: "#52645a", fontSize: 14, fontWeight: "600" },
  definitionValue: { color: "#17201c", fontSize: 16, lineHeight: 23 },
  actions: { gap: 10, paddingTop: 12 },
});
