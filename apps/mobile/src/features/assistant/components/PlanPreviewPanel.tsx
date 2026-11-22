import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
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
  state: "loading" | "unavailable" | "declined" | "observed";
  value?: PlanPreviewMetadata;
};

export type PlanPreviewPanelProps = {
  observe: PlanPreviewObserver;
  /** In-memory scope for the selected preview. Change it whenever selection changes. */
  selectionScope: string;
};

export function PlanPreviewPanel({
  observe,
  selectionScope,
}: PlanPreviewPanelProps) {
  const session = useSyncExternalStore(
    sessionStore.subscribe,
    sessionStore.getSnapshot,
    sessionStore.getSnapshot,
  );
  const [lifetime, setLifetime] = useState({
    observe,
    selectionScope,
    version: 0,
  });
  if (
    lifetime.observe !== observe ||
    lifetime.selectionScope !== selectionScope
  ) {
    setLifetime({ observe, selectionScope, version: lifetime.version + 1 });
  }
  if (!matchesPreviewSession(session, session)) return null;
  return (
    <PlanPreviewObservation
      key={`${session.epoch}:${lifetime.version}`}
      session={session}
      observe={observe}
    />
  );
}

function PlanPreviewObservation({
  session,
  observe,
}: {
  session: SessionSnapshot;
  observe: PlanPreviewObserver;
}) {
  const [current, setObservation] = useState<Observation | null>(null);
  const pending = useRef<AbortController | null>(null);
  const value = current?.value;
  const expires = value ? previewExpiry(value) : null;

  useLayoutEffect(
    () => () => {
      pending.current?.abort();
      pending.current = null;
    },
    [],
  );

  useEffect(() => {
    if (expires === null || current === null) return;
    const timer = setTimeout(
      () =>
        setObservation((state) =>
          state === current ? { state: "unavailable" } : state,
        ),
      Math.max(0, expires - Date.now()),
    );
    return () => clearTimeout(timer);
  }, [current, expires]);

  const load = async () => {
    pending.current?.abort();
    const request = new AbortController();
    pending.current = request;
    setObservation({ state: "loading" });
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
      found ? { state: "observed", value: found } : { state: "unavailable" },
    );
  };

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
            setObservation({ state: "declined" });
          }}
        />
      </View>
    </View>
  );
}
