import { Link } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useSyncExternalStore } from "react";

import { signOutCurrentUser } from "../src/auth/firebaseSession";
import { sessionStore } from "../src/auth/sessionStore";

export default function HomeScreen() {
  const session = useSyncExternalStore(
    sessionStore.subscribe,
    sessionStore.getSnapshot,
    sessionStore.getSnapshot,
  );
  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.content}>
        <Text accessibilityRole="header" style={styles.title}>
          Personal Health
        </Text>
        <Text style={styles.body}>
          A private place for health details you choose to remember. Review your
          daily log or the context you keep in your Profile.
        </Text>
        {session.mode === "firebase" ? (
          <View style={styles.account}>
            <Text style={styles.accountText}>
              Signed in as {session.email ?? "your account"}
            </Text>
            <Pressable
              accessibilityRole="button"
              onPress={() => void signOutCurrentUser()}
            >
              <Text style={styles.signOut}>Sign out</Text>
            </Pressable>
            {session.message ? (
              <Text accessibilityRole="alert">{session.message}</Text>
            ) : null}
          </View>
        ) : null}
        <Link accessibilityRole="button" style={styles.link} href="/today">
          Open Today
        </Link>
        <Link
          accessibilityRole="button"
          style={styles.secondaryLink}
          href="/insights"
        >
          Open Insights
        </Link>
        <Link
          accessibilityRole="button"
          style={styles.secondaryLink}
          href="/add"
        >
          Add an entry
        </Link>
        <Link
          accessibilityRole="button"
          style={styles.secondaryLink}
          href="/profile"
        >
          Open your Profile
        </Link>
        <Link
          accessibilityRole="button"
          style={styles.secondaryLink}
          href="/planning"
        >
          Open Plan
        </Link>
        <Link
          accessibilityRole="button"
          style={styles.secondaryLink}
          href="/assistant"
        >
          Open Assistant
        </Link>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { backgroundColor: "#f7f9f7", flex: 1 },
  content: { flex: 1, gap: 18, justifyContent: "center", padding: 24 },
  title: { color: "#17201c", fontSize: 30, fontWeight: "700" },
  body: { color: "#46534d", fontSize: 17, lineHeight: 24 },
  link: {
    alignSelf: "flex-start",
    backgroundColor: "#245d3a",
    borderRadius: 12,
    color: "#fff",
    fontSize: 16,
    fontWeight: "700",
    overflow: "hidden",
    paddingHorizontal: 20,
    paddingVertical: 16,
  },
  secondaryLink: {
    alignSelf: "flex-start",
    backgroundColor: "#fff",
    borderColor: "#52645a",
    borderRadius: 12,
    borderWidth: 1,
    color: "#24342b",
    fontSize: 16,
    fontWeight: "700",
    overflow: "hidden",
    paddingHorizontal: 20,
    paddingVertical: 16,
  },
  account: { gap: 8 },
  accountText: { color: "#46534d", fontSize: 14 },
  signOut: { color: "#245d3a", fontSize: 16, fontWeight: "700" },
});
