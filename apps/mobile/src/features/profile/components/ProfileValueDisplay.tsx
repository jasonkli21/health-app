import { StyleSheet, Text, View } from "react-native";

import { formatProfileValue } from "../model";
import type { ProfilePayload } from "../model";

export function ProfileValueDisplay({
  value,
  label = "Value",
}: {
  value: ProfilePayload["value"];
  label?: string;
}) {
  const isUnknown = value === null;
  return (
    <View
      accessibilityLabel={`${label}: ${formatProfileValue(value)}`}
      style={styles.container}
    >
      <Text style={styles.label}>{label}</Text>
      <Text style={[styles.value, isUnknown && styles.unknown]}>
        {formatProfileValue(value)}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: "#f0f5f1",
    borderRadius: 12,
    gap: 4,
    padding: 16,
  },
  label: { color: "#4d5a54", fontSize: 14, fontWeight: "600" },
  value: { color: "#17201c", fontSize: 18, lineHeight: 25 },
  unknown: { color: "#596860", fontStyle: "italic" },
});
