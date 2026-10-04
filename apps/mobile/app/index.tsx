import { Text, View } from "react-native";

export default function HomeScreen() {
  return (
    <View
      style={{
        flex: 1,
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
      }}
    >
      <Text style={{ fontSize: 24, fontWeight: "600" }}>Personal Health</Text>
      <Text style={{ marginTop: 12, textAlign: "center" }}>
        Phase 0 scaffold only. See docs/implementation/implementation-plan.md
        before adding product features.
      </Text>
    </View>
  );
}
