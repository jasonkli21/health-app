import { useRef, useState } from "react";
import { useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";

import { profileApi, ProfileUserError } from "../api";
import { ProfileForm } from "../components/ProfileForm";
import { newProfileId } from "../model";
import type { BuiltProfileFields } from "../model";
import {
  activeProfileCreateRecovery,
  type ProfileCreateAttempt,
} from "../createRecovery";

export default function ProfileCreateScreen() {
  const router = useRouter();
  const recovery = activeProfileCreateRecovery;
  const itemId = useRef(recovery.retryOriginal()?.id ?? newProfileId());
  const [hasUncertainSave, setHasUncertainSave] = useState(
    recovery.isUncertain,
  );

  async function submitAttempt(attempt: ProfileCreateAttempt) {
    try {
      const item = await profileApi.createProfileItem({
        id: attempt.id,
        ...attempt.fields,
      });
      recovery.resolve();
      setHasUncertainSave(false);
      router.replace({
        pathname: "/profile/[itemId]",
        params: { itemId: item.id },
      });
    } catch (error) {
      const uncertain = recovery.markFailure(attempt, error);
      setHasUncertainSave(uncertain);
      if (uncertain) {
        throw new ProfileUserError(
          "The save result is uncertain. Retry the original save to check whether it completed.",
        );
      }
      throw error;
    }
  }

  async function create(fields: BuiltProfileFields) {
    const attempt = recovery.prepare(itemId.current, fields);
    await submitAttempt(attempt);
  }

  async function retryOriginalSave() {
    const attempt = recovery.retryOriginal();
    if (attempt) await submitAttempt(attempt);
  }

  return (
    <SafeAreaView style={{ backgroundColor: "#f7f9f7", flex: 1 }}>
      <ProfileForm
        submitLabel="Save Profile item"
        onCancel={() => router.back()}
        onSubmit={create}
        onRetryUncertain={hasUncertainSave ? retryOriginalSave : undefined}
      />
    </SafeAreaView>
  );
}
