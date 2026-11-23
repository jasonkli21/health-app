import {
  useCallback,
  useLayoutEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { AppState, Text, View } from "react-native";
import { useFocusEffect } from "expo-router";

import { sessionStore, type SessionSnapshot } from "../../../auth/sessionStore";
import {
  DispatchObservationLifetime,
  snapshotDispatchReview,
  validDispatchReview,
  type DispatchReview,
} from "../planDispatchSession";
import { matchesPreviewSession } from "../planPreviewSession";
import { Button } from "./AssistantControls";
import { PlanPreviewDetails } from "./PlanPreviewPanel";
import { styles } from "./assistantStyles";

export interface PlanDispatchPanelProps {
  selectionScope: string;
  originalKey: string;
  review: (signal: AbortSignal) => Promise<DispatchReview | null>;
  confirm: (review: DispatchReview, signal: AbortSignal) => Promise<void>;
  observe: (originalKey: string, signal: AbortSignal) => Promise<string | null>;
}

export function PlanDispatchPanel(props: PlanDispatchPanelProps) {
  const session = useSyncExternalStore(
    sessionStore.subscribe,
    sessionStore.getSnapshot,
    sessionStore.getSnapshot,
  );
  const [composition, setComposition] = useState({ props, version: 0 });
  if (
    props.selectionScope !== composition.props.selectionScope ||
    props.originalKey !== composition.props.originalKey ||
    props.review !== composition.props.review ||
    props.confirm !== composition.props.confirm ||
    props.observe !== composition.props.observe
  ) {
    setComposition({ props, version: composition.version + 1 });
    return null;
  }
  return matchesPreviewSession(session, session) ? (
    <DispatchObservation
      key={`${session.epoch}:${composition.version}`}
      session={session}
      {...props}
    />
  ) : null;
}

function DispatchObservation({
  session,
  originalKey,
  review,
  confirm,
  observe,
}: PlanDispatchPanelProps & { session: SessionSnapshot }) {
  const [lifetime] = useState(
    () => new DispatchObservationLifetime(sessionStore, session),
  );
  const [shown, setShown] = useState<DispatchReview | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const operation = useRef<object | null>(null);

  const clear = useCallback(() => {
    lifetime.invalidate();
    operation.current = null;
    setShown(null);
    setResult(null);
    setMessage(null);
    setBusy(false);
  }, [lifetime]);

  useFocusEffect(
    useCallback(() => {
      if (AppState.currentState === "active") lifetime.activate();
      const subscription = AppState.addEventListener("change", (state) => {
        if (state === "active") lifetime.activate();
        else clear();
      });
      return () => {
        subscription.remove();
        clear();
      };
    }, [clear, lifetime]),
  );
  useLayoutEffect(() => () => lifetime.invalidate(), [lifetime]);

  useLayoutEffect(() => {
    if (!shown) return;
    const remaining = Date.parse(shown.preview.expires_at) - Date.now();
    const timeout = setTimeout(() => setShown(null), Math.max(0, remaining));
    return () => clearTimeout(timeout);
  }, [shown]);

  const run = async <T,>(
    action: (signal: AbortSignal) => Promise<T>,
    publish: (value: T) => void,
    feedback: string,
  ) => {
    if (operation.current || !lifetime.current()) return;
    const request = {};
    operation.current = request;
    setBusy(true);
    setShown(null);
    setResult(null);
    setMessage(null);
    const completed = await lifetime.run(action);
    if (operation.current !== request || !lifetime.current()) return;
    operation.current = null;
    setBusy(false);
    if (!completed) setMessage(feedback);
    else publish(completed.result);
  };

  return (
    <View style={styles.notice}>
      <Text accessibilityRole="header" style={styles.sectionTitle}>
        Synthetic Personal AI dispatch
      </Text>
      {shown && validDispatchReview(shown) ? (
        <>
          <PlanPreviewDetails preview={shown.preview} />
          <Button
            label="Confirm this dispatch"
            disabled={busy}
            onPress={() => {
              if (!validDispatchReview(shown)) return;
              void run(
                (signal) => confirm(shown, signal),
                () => setMessage("Check this dispatch for its result."),
                "Dispatch outcome is uncertain. Check this dispatch for its result.",
              );
            }}
          />
        </>
      ) : null}
      {message ? <Text accessibilityLiveRegion="polite">{message}</Text> : null}
      {result !== null ? (
        <Text accessibilityLiveRegion="polite">{result}</Text>
      ) : null}
      <View style={styles.linkRow}>
        <Button
          label="Review synthetic dispatch"
          disabled={busy}
          onPress={() =>
            void run(
              review,
              (value) => {
                if (
                  value &&
                  value.originalKey === originalKey &&
                  validDispatchReview(value)
                )
                  setShown(snapshotDispatchReview(value));
                else setMessage("No current dispatch preview is available.");
              },
              "No current dispatch preview is available.",
            )
          }
        />
        <Button
          label="Check original dispatch"
          disabled={busy}
          onPress={() =>
            void run(
              (signal) => observe(originalKey, signal),
              (value) => {
                if (value === null) setMessage("No result is available.");
                else setResult(value);
              },
              "No result is available.",
            )
          }
        />
      </View>
    </View>
  );
}
