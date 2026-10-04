import { useCallback, useRef, useState } from "react";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";

import { profileApi, profileErrorMessage } from "../api";
import { ProfileForm } from "../components/ProfileForm";
import { LoadingMessage, StatusMessage, ActionButton } from "../components/Ui";
import type { BuiltProfileFields } from "../model";
import {
  acceptProfileRefresh,
  EMPTY_PROFILE_EDIT_STATE,
  recordProfileDraft,
} from "../editState";

export default function ProfileEditScreen() {
  const { itemId } = useLocalSearchParams<{ itemId: string }>();
  const router = useRouter();
  const [editState, setEditState] = useState(EMPTY_PROFILE_EDIT_STATE);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const explicitlyReloading = useRef(false);
  const item = editState.item?.id === itemId ? editState.item : null;

  useFocusEffect(
    useCallback(() => {
      let current = true;
      const replaceDraft = explicitlyReloading.current;
      setLoading(true);
      setError(null);
      void profileApi
        .getProfileItem({ item_id: itemId })
        .then(
          (value) => {
            if (current) {
              explicitlyReloading.current = false;
              setEditState((state) =>
                acceptProfileRefresh(state, value, replaceDraft),
              );
            }
          },
          (requestError: unknown) => {
            if (current) {
              explicitlyReloading.current = false;
              setError(profileErrorMessage(requestError));
            }
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
    setEditState((state) => acceptProfileRefresh(state, updated, true));
    router.replace({
      pathname: "/profile/[itemId]",
      params: { itemId: updated.id },
    });
  }

  return (
    <SafeAreaView style={{ backgroundColor: "#f7f9f7", flex: 1 }}>
      {loading && !item ? (
        <LoadingMessage label="Loading Profile item" />
      ) : null}
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
      {item?.status === "archived" ? (
        <StatusMessage
          title="This item is archived"
          message="Archived Profile items are read-only."
        />
      ) : null}
      {item?.status === "active" && editState.draft ? (
        <ProfileForm
          key={`${item.id}:${editState.formGeneration}`}
          initialDraft={editState.draft}
          submitLabel="Save changes"
          onCancel={() => router.back()}
          onSubmit={save}
          onDraftChange={(draft) =>
            setEditState((state) => recordProfileDraft(state, draft))
          }
          onConflictReload={() => {
            explicitlyReloading.current = true;
            setReload((value) => value + 1);
          }}
        />
      ) : null}
    </SafeAreaView>
  );
}
