import { useRef } from "react";
import { useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";

import { profileApi } from "../api";
import { ProfileForm } from "../components/ProfileForm";
import { newProfileId } from "../model";
import type { BuiltProfileFields } from "../model";

export default function ProfileCreateScreen() {
  const router = useRouter();
  const itemId = useRef(newProfileId());

  async function create(fields: BuiltProfileFields) {
    const item = await profileApi.createProfileItem({
      id: itemId.current,
      ...fields,
    });
    router.replace({
      pathname: "/profile/[itemId]",
      params: { itemId: item.id },
    });
  }

  return (
    <SafeAreaView style={{ backgroundColor: "#f7f9f7", flex: 1 }}>
      <ProfileForm
        submitLabel="Save Profile item"
        onCancel={() => router.back()}
        onSubmit={create}
      />
    </SafeAreaView>
  );
}
