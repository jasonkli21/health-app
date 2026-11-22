import type { SessionSnapshot, SessionStore } from "../../auth/sessionStore";

export interface PlanPreviewMetadata {
  history_turns: number;
  source_sensitivity: "restricted";
  expires_at: string;
  destination: {
    application: "health";
    provider: string;
    model: string;
    runtime: string;
    recipient: string;
  };
}

export type PlanPreviewObserver = (
  signal: AbortSignal,
) => Promise<PlanPreviewMetadata | null>;

export function matchesPreviewSession(
  start: SessionSnapshot,
  current: SessionSnapshot,
): boolean {
  return (
    start.mode === "firebase" &&
    start.status === "signed_in" &&
    start.userId !== null &&
    current.status === "signed_in" &&
    current.epoch === start.epoch &&
    current.userId === start.userId
  );
}

export function previewExpiry(value: PlanPreviewMetadata, now = Date.now()) {
  const expiry = Date.parse(value.expires_at);
  return value.source_sensitivity === "restricted" &&
    value.destination.application === "health" &&
    Number.isInteger(value.history_turns) &&
    value.history_turns > 0 &&
    expiry > now
    ? expiry
    : null;
}

export async function observeCurrentPlanPreview(
  sessions: SessionStore,
  start: SessionSnapshot,
  observe: PlanPreviewObserver,
  signal: AbortSignal,
): Promise<PlanPreviewMetadata | null> {
  if (signal.aborted || !matchesPreviewSession(start, sessions.getSnapshot())) {
    return null;
  }
  try {
    const value = await observe(signal);
    if (
      signal.aborted ||
      !matchesPreviewSession(start, sessions.getSnapshot()) ||
      !value ||
      previewExpiry(value) === null
    )
      return null;
    const { application, provider, model, runtime, recipient } =
      value.destination;
    return {
      history_turns: value.history_turns,
      source_sensitivity: value.source_sensitivity,
      expires_at: value.expires_at,
      destination: { application, provider, model, runtime, recipient },
    };
  } catch {
    return null;
  }
}
