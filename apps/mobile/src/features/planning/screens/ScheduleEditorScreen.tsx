import { useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useRef, useState } from "react";
import {
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import type { components } from "@personal-health/api-client";
import { ApiError } from "@personal-health/api-client";

import {
  ActionButton,
  LoadingMessage,
  StatusMessage,
} from "../../profile/components/Ui";
import { DEVICE_TIMEZONE, localCalendarDate } from "../../daily/model";
import { sessionStore } from "../../../auth/sessionStore";
import { planningApi, planningErrorMessage } from "../api";

type ParentKind = "regimen" | "plan";
type Schedule = components["schemas"]["ScheduleDefinitionV1"];
const WEEKDAYS = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];

function addDays(value: string, amount: number): string {
  const date = new Date(`${value}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + amount);
  return date.toISOString().slice(0, 10);
}

function laterDate(left: string, right: string): string {
  return left > right ? left : right;
}

export default function ScheduleEditorScreen() {
  const params = useLocalSearchParams<{
    parentKind?: string;
    parentId?: string;
    itemId?: string;
    label?: string;
  }>();
  const router = useRouter();
  const parentKind = params.parentKind as ParentKind;
  const validRoute = Boolean(
    params.parentId &&
      (parentKind === "regimen" || parentKind === "plan") &&
      (parentKind !== "plan" || params.itemId),
  );
  const today = localCalendarDate();
  const [current, setCurrent] = useState<
    components["schemas"]["ScheduleResponse"] | null
  >(null);
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);
  const [reloadRequired, setReloadRequired] = useState(false);
  const initialized = useRef(false);
  const replaceDraftOnReload = useRef(false);
  const baselineRevision = useRef<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [localTime, setLocalTime] = useState("08:00");
  const [timezone, setTimezone] = useState(DEVICE_TIMEZONE);
  const [startDate, setStartDate] = useState(today);
  const [effectiveFrom, setEffectiveFrom] = useState(today);
  const [endDate, setEndDate] = useState("");
  const [recurrence, setRecurrence] = useState<"daily" | "weekly">("daily");
  const [interval, setInterval] = useState("1");
  const [weekdays, setWeekdays] = useState<number[]>([]);

  useEffect(() => {
    if (!validRoute || !params.parentId) return;
    let active = true;
    const request =
      parentKind === "regimen"
        ? planningApi.getRegimenSchedule({ regimen_id: params.parentId })
        : planningApi.getPlanItemSchedule({
            plan_id: params.parentId,
            item_id: params.itemId!,
          });
    setLoading(!initialized.current || replaceDraftOnReload.current);
    request
      .then((schedule) => {
        if (!active) return;
        if (initialized.current && !replaceDraftOnReload.current) {
          if (
            baselineRevision.current !== (schedule?.schedule_revision ?? null)
          ) {
            setReloadRequired(true);
            setError(
              "The schedule changed. Reload it before saving this draft.",
            );
          }
          return;
        }
        replaceDraftOnReload.current = false;
        baselineRevision.current = schedule?.schedule_revision ?? null;
        setLoaded(true);
        setError(null);
        setReloadRequired(false);
        setCurrent(schedule);
        initialized.current = true;
        if (!schedule) {
          setLocalTime("08:00");
          setTimezone(DEVICE_TIMEZONE);
          setStartDate(today);
          setEffectiveFrom(today);
          setEndDate("");
          setRecurrence("daily");
          setInterval("1");
          setWeekdays([]);
          return;
        }
        setLocalTime(schedule.schedule.local_time.slice(0, 5));
        setTimezone(schedule.schedule.timezone);
        setStartDate(schedule.schedule.start_date);
        setEndDate(schedule.schedule.end_date ?? "");
        setRecurrence(schedule.schedule.recurrence);
        setInterval(String(schedule.schedule.interval));
        setWeekdays(schedule.schedule.weekdays ?? []);
        setEffectiveFrom(
          laterDate(addDays(today, 1), addDays(schedule.effective_from, 1)),
        );
      })
      .catch((requestError: unknown) => {
        if (active) setError(planningErrorMessage(requestError));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [
    parentKind,
    params.itemId,
    params.parentId,
    today,
    validRoute,
    reloadToken,
  ]);

  async function save() {
    const sessionAtStart = sessionStore.getSnapshot();
    const isCurrentSession = () => {
      const latest = sessionStore.getSnapshot();
      return (
        latest.epoch === sessionAtStart.epoch &&
        latest.userId === sessionAtStart.userId
      );
    };
    setError(null);
    if (reloadRequired) {
      setError("Reload the latest schedule before saving this draft.");
      return;
    }
    if (!loaded) {
      setError("Load the current schedule before saving changes.");
      return;
    }
    if (
      !params.parentId ||
      (parentKind !== "regimen" && parentKind !== "plan") ||
      (parentKind === "plan" && !params.itemId)
    ) {
      setError("This schedule is missing its planning item.");
      return;
    }
    if (
      !/^\d{4}-\d{2}-\d{2}$/.test(startDate) ||
      !/^\d{4}-\d{2}-\d{2}$/.test(effectiveFrom) ||
      (endDate && !/^\d{4}-\d{2}-\d{2}$/.test(endDate))
    ) {
      setError("Dates must use YYYY-MM-DD.");
      return;
    }
    if (!/^\d{2}:\d{2}$/.test(localTime) || !timezone.trim()) {
      setError("Enter a local time and IANA timezone.");
      return;
    }
    const intervalValue = Number(interval);
    if (
      !Number.isInteger(intervalValue) ||
      intervalValue < 1 ||
      intervalValue > 365
    ) {
      setError("Repeat interval must be from 1 through 365.");
      return;
    }
    if (recurrence === "weekly" && weekdays.length === 0) {
      setError("Choose at least one weekday for a weekly schedule.");
      return;
    }
    const schedule: Schedule = {
      start_date: startDate,
      local_time: `${localTime}:00`,
      timezone: timezone.trim(),
      recurrence,
      interval: intervalValue,
      weekdays:
        recurrence === "weekly" ? [...weekdays].sort((a, b) => a - b) : [],
      end_date: endDate || null,
    };
    setBusy(true);
    try {
      const body = {
        effective_from: effectiveFrom,
        expected_schedule_revision: current?.schedule_revision ?? null,
        schedule,
      };
      if (parentKind === "regimen") {
        await planningApi.editRegimenSchedule(
          { regimen_id: params.parentId },
          body,
        );
      } else {
        await planningApi.editPlanItemSchedule(
          { plan_id: params.parentId, item_id: params.itemId! },
          body,
        );
      }
      if (!isCurrentSession()) return;
      router.back();
    } catch (requestError) {
      if (!isCurrentSession()) return;
      setReloadRequired(
        requestError instanceof ApiError && requestError.status === 409,
      );
      setError(
        `${planningErrorMessage(requestError)} Reload the schedule before trying again.`,
      );
    } finally {
      if (isCurrentSession()) setBusy(false);
    }
  }

  if (!validRoute) {
    return (
      <SafeAreaView style={styles.safeArea}>
        <StatusMessage
          title="Schedule link is incomplete"
          message="Return to Plan and open the regimen or plan item again."
          tone="error"
        />
        <ActionButton label="Back" onPress={() => router.back()} />
      </SafeAreaView>
    );
  }
  if (loading) return <LoadingMessage label="Loading schedule" />;
  if (!loaded) {
    return (
      <SafeAreaView style={styles.safeArea}>
        <StatusMessage
          title="Schedule not loaded"
          message={error ?? "Load the current schedule before editing it."}
          tone="error"
        />
        <ActionButton
          label="Retry loading schedule"
          onPress={() => setReloadToken((value) => value + 1)}
        />
        <ActionButton label="Back" secondary onPress={() => router.back()} />
      </SafeAreaView>
    );
  }
  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text accessibilityRole="header" style={styles.title}>
          Edit schedule
        </Text>
        <Text style={styles.subtitle}>
          {params.label ? `Schedule for ${params.label}. ` : ""}Changing a
          schedule preserves earlier occurrence history. Edits take effect on
          the selected future date.
        </Text>
        {error ? (
          <StatusMessage
            title="Could not save schedule"
            message={error}
            tone="error"
          />
        ) : null}
        {!loaded || reloadRequired ? (
          <ActionButton
            label={
              reloadRequired
                ? "Reload latest schedule and replace this draft"
                : "Retry loading schedule"
            }
            secondary
            onPress={() => {
              replaceDraftOnReload.current = true;
              setReloadToken((value) => value + 1);
            }}
          />
        ) : null}
        <Input
          label="Local time (HH:MM)"
          value={localTime}
          onChange={setLocalTime}
          placeholder="08:00"
        />
        <Input
          label="IANA timezone"
          value={timezone}
          onChange={setTimezone}
          placeholder="America/Los_Angeles"
        />
        <Input
          label="Schedule starts on (YYYY-MM-DD)"
          value={startDate}
          onChange={setStartDate}
        />
        <Input
          label="Effective from (YYYY-MM-DD)"
          value={effectiveFrom}
          onChange={setEffectiveFrom}
        />
        <Input
          label="Optional end date (YYYY-MM-DD)"
          value={endDate}
          onChange={setEndDate}
        />
        <Choices
          label="Repeat"
          options={["daily", "weekly"]}
          value={recurrence}
          onChange={setRecurrence}
        />
        <Input
          label="Every N days or weeks"
          value={interval}
          onChange={setInterval}
          keyboardType="number-pad"
        />
        {recurrence === "weekly" ? (
          <View style={styles.group}>
            <Text style={styles.label}>On weekdays</Text>
            <View style={styles.choices}>
              {WEEKDAYS.map((day, index) => {
                const selected = weekdays.includes(index);
                return (
                  <Pressable
                    key={day}
                    accessibilityRole="button"
                    accessibilityLabel={day}
                    accessibilityState={{ selected }}
                    onPress={() =>
                      setWeekdays((values) =>
                        selected
                          ? values.filter((value) => value !== index)
                          : [...values, index],
                      )
                    }
                    style={[styles.choice, selected && styles.selected]}
                  >
                    <Text
                      style={[
                        styles.choiceText,
                        selected && styles.selectedText,
                      ]}
                    >
                      {day.slice(0, 3)}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
          </View>
        ) : null}
        <ActionButton
          label="Save schedule"
          busy={busy}
          disabled={reloadRequired}
          onPress={() => void save()}
        />
        <ActionButton
          label="Cancel"
          secondary
          disabled={busy}
          onPress={() => router.back()}
        />
      </ScrollView>
    </SafeAreaView>
  );
}

function Input({
  label,
  value,
  onChange,
  placeholder,
  keyboardType,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  keyboardType?: "default" | "number-pad";
}) {
  return (
    <View style={styles.group}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        value={value}
        onChangeText={onChange}
        placeholder={placeholder}
        keyboardType={keyboardType ?? "default"}
        autoCapitalize="none"
        style={styles.input}
      />
    </View>
  );
}

function Choices<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: readonly T[];
  value: string;
  onChange: (value: T) => void;
}) {
  return (
    <View style={styles.group}>
      <Text style={styles.label}>{label}</Text>
      <View style={styles.choices}>
        {options.map((option) => (
          <Pressable
            key={option}
            accessibilityRole="button"
            accessibilityState={{ selected: option === value }}
            onPress={() => onChange(option)}
            style={[styles.choice, option === value && styles.selected]}
          >
            <Text
              style={[
                styles.choiceText,
                option === value && styles.selectedText,
              ]}
            >
              {option}
            </Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: "#f7f9f7" },
  content: { gap: 16, padding: 20, paddingBottom: 36 },
  title: { color: "#17201c", fontSize: 28, fontWeight: "700" },
  subtitle: { color: "#46534d", fontSize: 15, lineHeight: 22 },
  group: { gap: 6 },
  label: { color: "#203a2e", fontSize: 15, fontWeight: "700" },
  input: {
    backgroundColor: "#fff",
    borderColor: "#68786f",
    borderRadius: 10,
    borderWidth: 1,
    color: "#17201c",
    fontSize: 16,
    minHeight: 50,
    paddingHorizontal: 14,
  },
  choices: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  choice: {
    backgroundColor: "#fff",
    borderColor: "#68786f",
    borderRadius: 18,
    borderWidth: 1,
    paddingHorizontal: 13,
    paddingVertical: 9,
  },
  selected: { backgroundColor: "#245d3a", borderColor: "#245d3a" },
  choiceText: { color: "#24342b", fontSize: 14, textTransform: "capitalize" },
  selectedText: { color: "#fff", fontWeight: "700" },
});
