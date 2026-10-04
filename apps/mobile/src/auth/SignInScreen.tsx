import { useState, useSyncExternalStore } from "react";
import {
  Pressable,
  SafeAreaView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { sessionStore } from "./sessionStore";
import { signIn } from "./firebaseSession";

export function SignInScreen() {
  const session = useSyncExternalStore(
    sessionStore.subscribe,
    sessionStore.getSnapshot,
    sessionStore.getSnapshot,
  );
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await signIn(email, password);
    } catch {
      setError(
        "Sign-in failed. Check your email and password, then try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <SafeAreaView style={styles.page}>
      <View style={styles.content}>
        <Text accessibilityRole="header" style={styles.title}>
          Sign in
        </Text>
        {session.status === "unavailable" ? (
          <Text accessibilityRole="alert" style={styles.error}>
            {session.message}
          </Text>
        ) : null}
        {session.status === "initializing" ? (
          <Text accessibilityLiveRegion="polite">
            Restoring your secure session…
          </Text>
        ) : null}
        {session.status === "expired" ? (
          <Text accessibilityRole="alert" style={styles.error}>
            {session.message}
          </Text>
        ) : null}
        <TextInput
          accessibilityLabel="Email"
          autoCapitalize="none"
          autoComplete="email"
          keyboardType="email-address"
          style={styles.input}
          value={email}
          onChangeText={setEmail}
          editable={!busy && session.status !== "unavailable"}
        />
        <TextInput
          accessibilityLabel="Password"
          autoComplete="password"
          secureTextEntry
          style={styles.input}
          value={password}
          onChangeText={setPassword}
          editable={!busy && session.status !== "unavailable"}
        />
        {error ? (
          <Text accessibilityRole="alert" style={styles.error}>
            {error}
          </Text>
        ) : null}
        <Pressable
          accessibilityRole="button"
          disabled={
            busy ||
            session.status === "unavailable" ||
            session.status === "initializing"
          }
          onPress={() => void submit()}
          style={styles.button}
        >
          <Text style={styles.buttonText}>
            {busy ? "Signing in…" : "Continue"}
          </Text>
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: "#f7f9f7" },
  content: { flex: 1, justifyContent: "center", gap: 16, padding: 24 },
  title: { color: "#17201c", fontSize: 30, fontWeight: "700" },
  input: {
    backgroundColor: "#fff",
    borderColor: "#52645a",
    borderRadius: 10,
    borderWidth: 1,
    padding: 14,
  },
  error: { color: "#9d1f1f" },
  button: {
    alignItems: "center",
    backgroundColor: "#245d3a",
    borderRadius: 12,
    padding: 16,
  },
  buttonText: { color: "#fff", fontSize: 16, fontWeight: "700" },
});
