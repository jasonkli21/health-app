import { useCallback, useState } from "react";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";

import { profileApi, profileErrorMessage } from "../api";
import { ProfileForm } from "../components/ProfileForm";
import { LoadingMessage, StatusMessage, ActionButton } from "../components/Ui";
import {
  draftFromProfile,
  type BuiltProfileFields,
  type ProfileItem,
} from "../model";

export default function ProfileEditScreen() {
  const { itemId } = useLocalSearchParams<{ itemId: string }>();
  const router = useRouter();
  const [item, setItem] = useState<ProfileItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

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

  async function save(fields: BuiltProfileFields) {
    if (!item) return;
    const updated = await profileApi.updateProfileItem(
      { item_id: item.id },
      { expected_revision: item.revision, ...fields },
    );
    setItem(updated);
    router.replace({
      pathname: "/profile/[itemId]",
      params: { itemId: updated.id },
    });
  }

  return (
    <SafeAreaView style={{ backgroundColor: "#f7f9f7", flex: 1 }}>
      {loading ? <LoadingMessage label="Loading Profile item" /> : null}
      {error ? (
        <>
          <StatusMessage
            title="Profile item could not load"
            message={error}
            tone="error"
          />
          <ActionButton
            label="Retry Profile request"
            onPress={() => setReload((value) => value + 1)}
          />
        </>
      ) : null}
      {!loading && item?.status === "archived" ? (
        <StatusMessage
          title="This item is archived"
          message="Archived Profile items are read-only."
        />
      ) : null}
      {!loading && !error && item?.status === "active" ? (
        <ProfileForm
          key={`${item.id}:${item.revision}`}
          initialDraft={draftFromProfile(item)}
          submitLabel="Save changes"
          onCancel={() => router.back()}
          onSubmit={save}
          onConflictReload={() => setReload((value) => value + 1)}
        />
      ) : null}
    </SafeAreaView>
  );
}
