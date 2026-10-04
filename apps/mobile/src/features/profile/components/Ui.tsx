import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";

export function ActionButton({
  label,
  onPress,
  disabled = false,
  busy = false,
  secondary = false,
  hint,
}: {
  label: string;
  onPress: () => void;
  disabled?: boolean;
  busy?: boolean;
  secondary?: boolean;
  hint?: string;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint={hint}
      accessibilityState={{ disabled: disabled || busy, busy }}
      disabled={disabled || busy}
      onPress={onPress}
      style={[
        styles.button,
        secondary ? styles.secondary : styles.primary,
        (disabled || busy) && styles.disabled,
      ]}
    >
      {busy ? (
        <ActivityIndicator color={secondary ? "#245d3a" : "#fff"} />
      ) : null}
      <Text style={[styles.buttonText, secondary && styles.secondaryText]}>
        {label}
      </Text>
    </Pressable>
  );
}

export function StatusMessage({
  title,
  message,
  tone = "neutral",
}: {
  title: string;
  message: string;
  tone?: "neutral" | "error";
}) {
  return (
    <View accessibilityLiveRegion="polite" style={styles.status}>
      <Text
        accessibilityRole={tone === "error" ? "alert" : "header"}
        style={styles.statusTitle}
      >
        {title}
      </Text>
      <Text
        style={[styles.statusMessage, tone === "error" && styles.errorText]}
      >
        {message}
      </Text>
    </View>
  );
}

export function LoadingMessage({
  label = "Loading Profile",
}: {
  label?: string;
}) {
  return (
    <View
      accessibilityLabel={label}
      accessibilityRole="progressbar"
      style={styles.loading}
    >
      <ActivityIndicator size="large" color="#245d3a" />
      <Text style={styles.statusMessage}>{label}…</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  button: {
    alignItems: "center",
    borderRadius: 12,
    flexDirection: "row",
    gap: 8,
    justifyContent: "center",
    minHeight: 52,
    paddingHorizontal: 18,
  },
  primary: { backgroundColor: "#245d3a" },
  secondary: {
    backgroundColor: "#fff",
    borderColor: "#52645a",
    borderWidth: 1,
  },
  buttonText: { color: "#fff", fontSize: 16, fontWeight: "700" },
  secondaryText: { color: "#24342b" },
  disabled: { opacity: 0.55 },
  status: { gap: 8, padding: 20 },
  statusTitle: { color: "#17201c", fontSize: 20, fontWeight: "700" },
  statusMessage: { color: "#46534d", fontSize: 16, lineHeight: 23 },
  errorText: { color: "#9b1c1c" },
  loading: {
    alignItems: "center",
    gap: 16,
    justifyContent: "center",
    minHeight: 180,
  },
});
