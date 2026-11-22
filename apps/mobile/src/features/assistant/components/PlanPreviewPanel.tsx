import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Text, View } from "react-native";

import { sessionStore, type SessionSnapshot } from "../../../auth/sessionStore";
import {
  matchesPreviewSession,
  observeCurrentPlanPreview,
  previewExpiry,
  type PlanPreviewMetadata,
  type PlanPreviewObserver,
} from "../planPreviewSession";
import { Button } from "./AssistantControls";
import { styles } from "./assistantStyles";

export function PlanPreviewDetails({
  preview,
}: {
  preview: PlanPreviewMetadata;
}) {
  const target = preview.destination;
  return (
    <>
      <Text style={styles.body}>Health profile preferences · record field</Text>
      <Text style={styles.body}>Sensitivity · Restricted</Text>
      <Text style={styles.body}>
        Destination · {target.provider} · {target.model} · {target.runtime} ·{" "}
        {target.recipient}
      </Text>
      <Text style={styles.body}>Includes a Personal AI memory item</Text>
      <Text style={styles.body}>
        Conversation turns · {preview.history_turns}
      </Text>
      <Text style={styles.body}>
        Expires · {new Date(preview.expires_at).toLocaleTimeString()}
      </Text>
    </>
  );
}

type Observation = {
  session: SessionSnapshot;
  observer: PlanPreviewObserver;
  state: "loading" | "unavailable" | "declined" | "observed";
  value?: PlanPreviewMetadata;
};

export function PlanPreviewPanel({
  observe,
}: {
  observe: PlanPreviewObserver;
}) {
  const session = useSyncExternalStore(
    sessionStore.subscribe,
    sessionStore.getSnapshot,
    sessionStore.getSnapshot,
  );
  const [observation, setObservation] = useState<Observation | null>(null);
  const pending = useRef<AbortController | null>(null);
  const current =
    observation &&
    observation.observer === observe &&
    matchesPreviewSession(observation.session, session)
      ? observation
      : null;
  const value = current?.value;
  const expires = value ? previewExpiry(value) : null;

  useEffect(
    () => () => {
      pending.current?.abort();
      pending.current = null;
    },
    [session.epoch, observe],
  );

  useEffect(() => {
    if (expires === null || current === null) return;
    const timer = setTimeout(
      () =>
        setObservation((state) =>
          state === current
            ? {
                session: current.session,
                observer: current.observer,
                state: "unavailable",
              }
            : state,
        ),
      Math.max(0, expires - Date.now()),
    );
    return () => clearTimeout(timer);
  }, [current, expires]);

  const load = async () => {
    pending.current?.abort();
    const request = new AbortController();
    pending.current = request;
    setObservation({ session, observer: observe, state: "loading" });
    const found = await observeCurrentPlanPreview(
      sessionStore,
      session,
      observe,
      request.signal,
    );
    if (pending.current !== request || request.signal.aborted) return;
    pending.current = null;
    if (!matchesPreviewSession(session, sessionStore.getSnapshot())) return;
    setObservation(
      found
        ? { session, observer: observe, state: "observed", value: found }
        : { session, observer: observe, state: "unavailable" },
    );
  };

  if (!matchesPreviewSession(session, session)) return null;
  return (
    <View style={styles.notice}>
      <Text accessibilityRole="header" style={styles.sectionTitle}>
        Personal AI plan preview
      </Text>
      <Text style={styles.body}>
        Review what the plan would use. AI responses are unavailable in this
        preview.
      </Text>
      {value && expires !== null ? (
        <PlanPreviewDetails preview={value} />
      ) : null}
      {current?.state === "unavailable" ? (
        <Text
          accessibilityRole="alert"
          accessibilityLiveRegion="polite"
          style={styles.body}
        >
          No current preview is available.
        </Text>
      ) : null}
      {current?.state === "declined" ? (
        <Text accessibilityLiveRegion="polite" style={styles.body}>
          Preview declined.
        </Text>
      ) : null}
      <View style={styles.linkRow}>
        <Button
          label={
            current?.state === "loading"
              ? "Checking preview…"
              : "Review preview"
          }
          disabled={current?.state === "loading"}
          onPress={() => void load()}
        />
        <Button
          label="Decline preview"
          onPress={() => {
            pending.current?.abort();
            pending.current = null;
            setObservation({ session, observer: observe, state: "declined" });
          }}
        />
      </View>
    </View>
  );
}
