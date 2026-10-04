import { ApiError } from "@personal-health/api-client";
import type { FetchLike, FetchResponse } from "@personal-health/api-client";

import type { SessionStore } from "./sessionStore";

export type TokenProvider = (forceRefresh: boolean) => Promise<string>;

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
  onExpired: (epoch: number) => void = (epoch) => store.markExpired(epoch),
): FetchLike {
  return async (input, init) => {
    const session = store.getSnapshot();
    if (session.mode === "dev") return fetcher(input, init);
    if (session.status !== "signed_in") throw new SignedOutError();

    const epoch = session.epoch;
    const assertCurrent = () => {
      const latest = store.getSnapshot();
      if (latest.epoch !== epoch || latest.status !== "signed_in")
        throw new SessionChangedError();
    };
    const send = async (forceRefresh: boolean): Promise<FetchResponse> => {
      const token = await tokenProvider(forceRefresh);
      assertCurrent();
      if (!token || token.length > 8192) throw new SignedOutError();
      const headers = { ...init?.headers, authorization: `Bearer ${token}` };
      const response = await fetcher(input, {
        ...(init ?? { method: "GET" }),
        headers,
      });
      assertCurrent();
      return response;
    };

    let response = await send(false);
    if (response.status !== 401) return response;
    assertCurrent();
    response = await send(true);
    if (response.status === 401) {
      onExpired(epoch);
      throw new ApiError(401);
    }
    return response;
  };
}
