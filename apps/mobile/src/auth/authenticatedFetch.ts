import { ApiError } from "@personal-health/api-client";
import type { FetchLike, FetchResponse } from "@personal-health/api-client";

import type { SessionStore } from "./sessionStore";
import { assertApiRequestUrl, apiBaseUrl } from "./apiConfig";

export type TokenProvider = (forceRefresh: boolean) => Promise<string>;
export type ExpiredSession = { epoch: number; userId: string };

const definitiveAuthCodes = new Set([
  "auth/user-disabled",
  "auth/user-token-expired",
  "auth/invalid-user-token",
  "auth/invalid-refresh-token",
  "auth/user-not-found",
]);

function isDefinitiveTokenFailure(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    typeof error.code === "string" &&
    definitiveAuthCodes.has(error.code)
  );
}

export class SessionChangedError extends Error {
  constructor() {
    super("The signed-in account changed while this request was running.");
    this.name = "SessionChangedError";
  }
}

export class SignedOutError extends Error {
  constructor() {
    super("Sign in before making this request.");
    this.name = "SignedOutError";
  }
}

export function createAuthenticatedFetch(
  store: SessionStore,
  tokenProvider: TokenProvider,
  fetcher: FetchLike = globalThis.fetch as FetchLike,
  onExpired: (session: ExpiredSession) => void = ({ epoch, userId }) => {
    store.markExpired(epoch, userId);
  },
  configuredBaseUrl = apiBaseUrl,
): FetchLike {
  return async (input, init) => {
    const session = store.getSnapshot();
    if (session.mode === "dev") return fetcher(input, init);
    if (session.status !== "signed_in") throw new SignedOutError();
    assertApiRequestUrl(input, configuredBaseUrl);

    const epoch = session.epoch;
    const assertCurrent = () => {
      const latest = store.getSnapshot();
      if (
        latest.epoch !== epoch ||
        latest.status !== "signed_in" ||
        latest.userId !== session.userId
      )
        throw new SessionChangedError();
    };
    const send = async (forceRefresh: boolean): Promise<FetchResponse> => {
      let token: string;
      try {
        token = await tokenProvider(forceRefresh);
      } catch (error) {
        assertCurrent();
        if (isDefinitiveTokenFailure(error)) {
          onExpired({ epoch, userId: session.userId! });
          throw new SignedOutError();
        }
        throw error;
      }
      assertCurrent();
      if (!token || token.length > 8192) throw new SignedOutError();
      const headers = { ...init?.headers, authorization: `Bearer ${token}` };
      const response = await fetcher(input, {
        ...(init ?? { method: "GET" }),
        headers,
      });
      assertCurrent();
      return {
        ok: response.ok,
        status: response.status,
        json: async () => {
          assertCurrent();
          try {
            return await response.json();
          } finally {
            assertCurrent();
          }
        },
      };
    };

    let response = await send(false);
    if (response.status !== 401) return response;
    assertCurrent();
    response = await send(true);
    assertCurrent();
    if (response.status === 401) {
      onExpired({ epoch, userId: session.userId! });
      throw new ApiError(401);
    }
    return response;
  };
}
