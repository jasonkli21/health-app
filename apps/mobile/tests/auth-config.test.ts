import { describe, expect, it, vi } from "vitest";
import { resolveApiBaseUrl, assertApiRequestUrl } from "../src/auth/apiConfig";
import { resolveAuthMode, SessionStore } from "../src/auth/sessionStore";
import { createAuthenticatedFetch } from "../src/auth/authenticatedFetch";

describe("Firebase API configuration", () => {
  it("fails closed on invalid auth modes and missing or insecure API URLs", () => {
    expect(() => resolveAuthMode("firebas")).toThrow();
    for (const value of [
      undefined,
      "",
      "http://api.example.test",
      "ftp://api.example.test",
      "https://user:pass@api.example.test",
      "https://api.example.test?token=x",
    ]) {
      expect(() => resolveApiBaseUrl("firebase", value)).toThrow();
    }
    expect(resolveApiBaseUrl("dev", undefined)).toBe("http://127.0.0.1:8000");
    expect(resolveApiBaseUrl("firebase", "https://api.example.test")).toBe(
      "https://api.example.test",
    );
    expect(() =>
      assertApiRequestUrl(
        "http://api.example.test/profile",
        "https://api.example.test",
      ),
    ).toThrow();
    expect(() =>
      assertApiRequestUrl(
        "https://other.example.test/profile",
        "https://api.example.test",
      ),
    ).toThrow();
  });

  it("does not acquire or transmit a token to an unconfigured endpoint", async () => {
    const store = new SessionStore("firebase");
    store.setSignedIn("owner", null);
    const token = vi.fn(async () => "secret");
    const network = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({}),
    }));
    const request = createAuthenticatedFetch(
      store,
      token,
      network,
      undefined,
      "https://api.example.test",
    );
    await expect(request("http://api.example.test/profile")).rejects.toThrow();
    await expect(
      request("https://evil.example.test/profile"),
    ).rejects.toThrow();
    expect(token).not.toHaveBeenCalled();
    expect(network).not.toHaveBeenCalled();
  });
});
