import { resolveAuthMode } from "./sessionStore";

export function resolveApiBaseUrl(
  mode: string | undefined,
  configuredUrl: string | undefined,
): string {
  const authMode = resolveAuthMode(mode);
  const value = configuredUrl?.trim();
  if (authMode === "dev") return value || "http://127.0.0.1:8000";
  if (!value) throw new Error("Firebase builds require an API URL.");
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new Error("Firebase builds require a valid HTTPS API URL.");
  }
  if (
    url.protocol !== "https:" ||
    !url.hostname ||
    url.username ||
    url.password ||
    url.search ||
    url.hash
  ) {
    throw new Error("Firebase builds require a valid HTTPS API URL.");
  }
  return value.replace(/\/$/, "");
}

export const apiBaseUrl = resolveApiBaseUrl(
  process.env.EXPO_PUBLIC_AUTH_MODE,
  process.env.EXPO_PUBLIC_API_URL,
);

export function assertApiRequestUrl(input: string, baseUrl = apiBaseUrl): void {
  const requested = new URL(input);
  const base = new URL(baseUrl);
  if (
    requested.protocol !== "https:" ||
    requested.origin !== base.origin ||
    (requested.pathname !== base.pathname.replace(/\/$/, "") &&
      !requested.pathname.startsWith(`${base.pathname.replace(/\/$/, "")}/`))
  )
    throw new Error(
      "Refusing to send a bearer token to an unconfigured API endpoint.",
    );
}
