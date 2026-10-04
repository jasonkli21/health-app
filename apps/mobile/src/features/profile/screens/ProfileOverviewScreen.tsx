import { useCallback, useRef, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";

import { profileApi, profileErrorMessage } from "../api";
import {
  formatInstant,
  formatProfileValue,
  PROFILE_CATEGORIES,
  type ProfileCategory,
  type ProfileItem,
} from "../model";
import { ActionButton, LoadingMessage, StatusMessage } from "../components/Ui";
import { RequestScope, requestNextPage } from "../requestScope";

const PAGE_SIZE = 50;

export default function ProfileOverviewScreen() {
  const router = useRouter();
  const [category, setCategory] = useState<ProfileCategory | null>(null);
  const [items, setItems] = useState<ProfileItem[]>([]);
  const [asOf, setAsOf] = useState<string | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const requestScope = useRef(new RequestScope());
  const scopeKey = `overview:${category ?? "all"}:${refresh}`;

  useFocusEffect(
    useCallback(() => {
      const scope = requestScope.current.start(scopeKey);
      setLoading(true);
      setError(null);
      setItems([]);
      setNextCursor(null);
      setAsOf(null);
      setLoadingMore(false);
      void (async () => {
        try {
          const result = await profileApi.listProfileItems({
            ...(category ? { category } : {}),
            limit: PAGE_SIZE,
          });
          if (!requestScope.current.isCurrent(scope)) return;
          setItems(result.items);
          setAsOf(result.as_of);
          setNextCursor(result.next_cursor);
        } catch (requestError) {
          if (requestScope.current.isCurrent(scope)) {
            setError(profileErrorMessage(requestError));
          }
        } finally {
          if (requestScope.current.isCurrent(scope)) setLoading(false);
        }
      })();
      return () => {
        requestScope.current.invalidate(scope);
      };
      // Retry state intentionally recreates this focus callback to refetch server truth.
      // eslint-disable-next-line react-hooks/exhaustive-deps -- retry token is an effect trigger.
    }, [category, refresh, scopeKey]),
  );

  async function loadMore() {
    if (!nextCursor || !asOf) return;
    const scope = requestScope.current.tokenFor(scopeKey);
    if (!scope) return;
    const cursor = nextCursor;
    const pageAsOf = asOf;
    await requestNextPage(
      requestScope.current,
      scope,
      cursor,
      () =>
        profileApi.listProfileItems({
          ...(category ? { category } : {}),
          as_of: pageAsOf,
          cursor,
          limit: PAGE_SIZE,
        }),
      {
        onStart: () => {
          setLoadingMore(true);
          setError(null);
        },
        onSuccess: (result) => {
          setItems((current) => [...current, ...result.items]);
          setNextCursor(result.next_cursor);
        },
        onError: (requestError) => setError(profileErrorMessage(requestError)),
        onFinish: () => setLoadingMore(false),
      },
    );
  }

  const visibleGroups = category
    ? PROFILE_CATEGORIES.filter((entry) => entry.value === category)
    : PROFILE_CATEGORIES;

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <View style={styles.headerCopy}>
            <Text accessibilityRole="header" style={styles.title}>
              Your Profile
            </Text>
            <Text style={styles.subtitle}>
              Optional information you choose to keep for yourself.
            </Text>
          </View>
          <ActionButton
            label="Add Profile item"
            hint="Create an optional fact, constraint, or preference."
            onPress={() => router.push("/profile/new")}
          />
        </View>

        <View
          style={styles.filters}
          accessibilityLabel="Filter Profile categories"
        >
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Show all Profile categories"
            accessibilityState={{ selected: category === null }}
            onPress={() => setCategory(null)}
            style={[styles.filter, category === null && styles.filterSelected]}
          >
            <Text
              style={[
                styles.filterText,
                category === null && styles.filterTextSelected,
              ]}
            >
              All
            </Text>
          </Pressable>
          {PROFILE_CATEGORIES.map((entry) => {
            const selected = category === entry.value;
            return (
              <Pressable
                key={entry.value}
                accessibilityRole="button"
                accessibilityLabel={`Show ${entry.label} Profile items`}
                accessibilityState={{ selected }}
                onPress={() => setCategory(entry.value)}
                style={[styles.filter, selected && styles.filterSelected]}
              >
                <Text
                  style={[
                    styles.filterText,
                    selected && styles.filterTextSelected,
                  ]}
                >
                  {entry.label}
                </Text>
              </Pressable>
            );
          })}
        </View>

        {error && !loading ? (
          <View>
            <StatusMessage
              title="Profile could not load"
              message={error}
              tone="error"
            />
            <ActionButton
              label="Retry Profile request"
              onPress={() => setRefresh((n) => n + 1)}
            />
          </View>
        ) : null}

        {loading ? <LoadingMessage /> : null}

        {!loading && !error && items.length === 0 ? (
          <View style={styles.empty}>
            <Text accessibilityRole="header" style={styles.emptyTitle}>
              No Profile items yet
            </Text>
            <Text style={styles.subtitle}>
              Add only the details you want to remember. You can leave a value
              unknown.
            </Text>
            <ActionButton
              label="Create your first Profile item"
              onPress={() => router.push("/profile/new")}
            />
          </View>
        ) : null}

        {!loading && items.length > 0
          ? visibleGroups.map((group) => {
              const groupItems = items.filter(
                (item) => item.profile.category === group.value,
              );
              if (groupItems.length === 0) return null;
              return (
                <View key={group.value} style={styles.group}>
                  {category === null ? (
                    <Text accessibilityRole="header" style={styles.groupTitle}>
                      {group.label}
                    </Text>
                  ) : null}
                  {groupItems.map((item) => (
                    <Pressable
                      key={item.id}
                      accessibilityRole="button"
                      accessibilityLabel={`${item.profile.label}. ${formatProfileValue(item.profile.value)}. ${group.label}.`}
                      accessibilityHint="Open Profile item details, permissions, and history."
                      onPress={() =>
                        router.push({
                          pathname: "/profile/[itemId]",
                          params: { itemId: item.id },
                        })
                      }
                      style={styles.itemCard}
                    >
                      <Text style={styles.itemTitle}>{item.profile.label}</Text>
                      <Text style={styles.itemValue}>
                        {formatProfileValue(item.profile.value)}
                      </Text>
                      {item.valid_from || item.valid_to ? (
                        <Text style={styles.itemMeta}>
                          Effective {formatInstant(item.valid_from)} —{" "}
                          {formatInstant(item.valid_to)}
                        </Text>
                      ) : null}
                    </Pressable>
                  ))}
                </View>
              );
            })
          : null}

        {!loading && nextCursor ? (
          <ActionButton
            label="Load more Profile items"
            onPress={() => void loadMore()}
            busy={loadingMore}
            disabled={loadingMore}
            secondary
          />
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { backgroundColor: "#f7f9f7", flex: 1 },
  content: { gap: 20, padding: 20, paddingBottom: 36 },
  header: { gap: 16 },
  headerCopy: { gap: 6 },
  title: { color: "#17201c", fontSize: 30, fontWeight: "700" },
  subtitle: { color: "#46534d", fontSize: 16, lineHeight: 23 },
  filters: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  filter: {
    alignItems: "center",
    backgroundColor: "#fff",
    borderColor: "#68786f",
    borderRadius: 22,
    borderWidth: 1,
    justifyContent: "center",
    minHeight: 46,
    paddingHorizontal: 14,
  },
  filterSelected: {
    backgroundColor: "#dcefe4",
    borderColor: "#245d3a",
    borderWidth: 2,
  },
  filterText: { color: "#24342b", fontSize: 14, fontWeight: "600" },
  filterTextSelected: { color: "#17492b" },
  group: { gap: 10 },
  groupTitle: { color: "#203a2e", fontSize: 20, fontWeight: "700" },
  itemCard: {
    backgroundColor: "#fff",
    borderColor: "#c8d2cb",
    borderRadius: 14,
    borderWidth: 1,
    gap: 6,
    minHeight: 76,
    padding: 16,
  },
  itemTitle: { color: "#17201c", fontSize: 17, fontWeight: "700" },
  itemValue: { color: "#34463b", fontSize: 16, lineHeight: 22 },
  itemMeta: { color: "#596860", fontSize: 14, lineHeight: 20 },
  empty: { alignItems: "flex-start", gap: 14, paddingVertical: 24 },
  emptyTitle: { color: "#17201c", fontSize: 22, fontWeight: "700" },
});
