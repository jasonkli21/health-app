import { useEffect, useSyncExternalStore } from "react";
import { Stack } from "expo-router";

import { clearOnSessionChange } from "../src/auth/cacheLifecycle";
import { startFirebaseSession } from "../src/auth/firebaseSession";
import { sessionStore } from "../src/auth/sessionStore";
import { activeDailyCreateRecovery } from "../src/features/daily/api";
import { activeProfileCreateRecovery } from "../src/features/profile/createRecovery";
import {
  activePlanningCreateRecovery,
  activeTrackerCreateRecovery,
} from "../src/features/planning/api";

export default function RootLayout() {
  const session = useSyncExternalStore(
    sessionStore.subscribe,
    sessionStore.getSnapshot,
    sessionStore.getSnapshot,
  );

  useEffect(() => {
    if (session.mode === "firebase") startFirebaseSession();
    return clearOnSessionChange(sessionStore, [
      () => activeProfileCreateRecovery.resolve(),
      () => activeDailyCreateRecovery.resolve(),
      () => activeTrackerCreateRecovery.resolve(),
      () => activePlanningCreateRecovery.resolve(),
    ]);
  }, [session.mode]);

  const signedIn = session.mode === "dev" || session.status === "signed_in";
  return (
    <Stack
      key={session.epoch}
      screenOptions={{ headerTitle: "Personal Health" }}
    >
      <Stack.Protected guard={signedIn}>
        <Stack.Screen name="index" />
        <Stack.Screen name="today" />
        <Stack.Screen name="insights" />
        <Stack.Screen name="analytics/evidence/[objectId]" />
        <Stack.Screen name="add" />
        <Stack.Screen name="profile/index" />
        <Stack.Screen name="planning/index" />
        <Stack.Screen name="planning/new" />
        <Stack.Screen name="planning/[kind]/[id]" />
        <Stack.Screen name="planning/log-tracker" />
        <Stack.Screen name="planning/reschedule" />
        <Stack.Screen name="planning/schedule" />
        <Stack.Screen name="planning/history" />
        <Stack.Screen name="planning/occurrence-history" />
        <Stack.Screen name="assistant" />
        <Stack.Screen name="profile/new" />
        <Stack.Screen name="profile/[itemId]" />
        <Stack.Screen name="profile/[itemId]/edit" />
        <Stack.Screen name="profile/[itemId]/history" />
        <Stack.Screen name="daily/item/[itemId]" />
        <Stack.Screen name="daily/item/[itemId]/edit" />
        <Stack.Screen name="daily/item/[itemId]/history" />
      </Stack.Protected>
      <Stack.Protected guard={!signedIn}>
        <Stack.Screen name="sign-in" options={{ headerShown: false }} />
      </Stack.Protected>
    </Stack>
  );
}
