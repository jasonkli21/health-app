export type MobileAuthMode = "dev" | "firebase";
export type SessionStatus =
  | "ready"
  | "initializing"
  | "signed_out"
  | "signed_in"
  | "unavailable"
  | "expired";

export type SessionSnapshot = {
  mode: MobileAuthMode;
  status: SessionStatus;
  epoch: number;
  userId: string | null;
  email: string | null;
  message: string | null;
};

export class SessionStore {
  private snapshot: SessionSnapshot;
  private listeners = new Set<() => void>();

  constructor(mode: MobileAuthMode) {
    this.snapshot = {
      mode,
      status: mode === "dev" ? "ready" : "initializing",
      epoch: 0,
      userId: null,
      email: null,
      message: null,
    };
  }

  getSnapshot = (): SessionSnapshot => this.snapshot;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  setInitializing(): void {
    this.update(
      { status: "initializing", userId: null, email: null, message: null },
      true,
    );
  }

  setSignedOut(): void {
    this.update(
      { status: "signed_out", userId: null, email: null, message: null },
      true,
    );
  }

  setSignedIn(
    userId: string,
    email: string | null,
    message: string | null = null,
  ): void {
    if (!userId) {
      this.setUnavailable("The identity provider returned an invalid account.");
      return;
    }
    const changed =
      this.snapshot.userId !== userId || this.snapshot.status !== "signed_in";
    this.update({ status: "signed_in", userId, email, message }, changed);
  }

  setUnavailable(message: string): void {
    this.update(
      { status: "unavailable", userId: null, email: null, message },
      true,
    );
  }

  markExpired(expectedEpoch: number): void {
    if (
      this.snapshot.epoch !== expectedEpoch ||
      this.snapshot.status !== "signed_in"
    )
      return;
    this.update(
      {
        status: "expired",
        userId: null,
        email: null,
        message: "Your session expired. Sign in again to continue.",
      },
      true,
    );
  }

  private update(
    next: Pick<SessionSnapshot, "status" | "userId" | "email" | "message">,
    bumpEpoch: boolean,
  ): void {
    const previous = this.snapshot;
    if (
      previous.status === next.status &&
      previous.userId === next.userId &&
      previous.email === next.email &&
      previous.message === next.message
    )
      return;
    this.snapshot = {
      ...previous,
      ...next,
      epoch: previous.epoch + (bumpEpoch ? 1 : 0),
    };
    for (const listener of this.listeners) listener();
  }
}

const mode: MobileAuthMode =
  process.env.EXPO_PUBLIC_AUTH_MODE === "firebase" ? "firebase" : "dev";
export const sessionStore = new SessionStore(mode);
