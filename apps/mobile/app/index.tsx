import { Link } from "expo-router";
import { StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

export default function HomeScreen() {
  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.content}>
        <Text accessibilityRole="header" style={styles.title}>
          Personal Health
        </Text>
        <Text style={styles.body}>
          A private place for health details you choose to remember. Start with
          your Profile.
        </Text>
        <Link accessibilityRole="button" style={styles.link} href="/profile">
          Open your Profile
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
});
