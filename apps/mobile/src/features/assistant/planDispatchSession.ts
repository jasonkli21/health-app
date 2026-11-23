import type { SessionSnapshot, SessionStore } from "../../auth/sessionStore";
import {
  matchesPreviewSession,
  previewExpiry,
  type PlanPreviewMetadata,
} from "./planPreviewSession";

export type DispatchReview = {
  originalKey: string;
  category: "profile_preferences";
  fields: readonly ["record"];
  preview: PlanPreviewMetadata;
};

export function validDispatchReview(review: DispatchReview) {
  const { destination } = review.preview;
  return (
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(
      review.originalKey,
    ) &&
    review.category === "profile_preferences" &&
    review.fields.length === 1 &&
    review.fields[0] === "record" &&
    destination.provider === "fake" &&
    destination.model === "fake" &&
    Boolean(destination.runtime) &&
    Boolean(destination.recipient) &&
    previewExpiry(review.preview) !== null
  );
}

export function snapshotDispatchReview(review: DispatchReview): DispatchReview {
  const { history_turns, source_sensitivity, expires_at, destination } =
    review.preview;
  const { application, provider, model, runtime, recipient } = destination;
  return Object.freeze({
    originalKey: review.originalKey,
    category: review.category,
    fields: Object.freeze(["record"] as const),
    preview: Object.freeze({
      history_turns,
      source_sensitivity,
      expires_at,
      destination: Object.freeze({
        application,
        provider,
        model,
        runtime,
        recipient,
      }),
    }),
  });
}

export class DispatchObservationLifetime {
  private active = false;
  private pending: AbortController | null = null;

  constructor(
    private readonly sessions: SessionStore,
    private readonly session: SessionSnapshot,
  ) {}

  activate() {
    this.active = true;
  }

  invalidate() {
    this.active = false;
    this.pending?.abort();
    this.pending = null;
  }

  current() {
    return (
      this.active &&
      matchesPreviewSession(this.session, this.sessions.getSnapshot())
    );
  }

  async run<T>(read: (signal: AbortSignal) => Promise<T>) {
    if (this.pending || !this.current()) return null;
    const request = new AbortController();
    this.pending = request;
    try {
      const result = await read(request.signal);
      if (this.pending === request && !request.signal.aborted && this.current())
        return { result };
    } catch {
      // Ambiguous outcomes are handled by explicit original-key observation.
    } finally {
      if (this.pending === request) this.pending = null;
    }
    return null;
  }
}
