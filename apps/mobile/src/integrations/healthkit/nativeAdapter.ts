export type HealthKitNativeCapability =
  | { status: "native_adapter_unavailable" }
  | { status: "unsupported_platform" };

/** Native HealthKit remains unavailable until a compatible iOS adapter is verified. */
export function getHealthKitNativeCapability(
  platform: "ios" | "android" | "web",
): HealthKitNativeCapability {
  return platform === "ios"
    ? { status: "native_adapter_unavailable" }
    : { status: "unsupported_platform" };
}

export const FIRST_WAVE_TYPES = [
  "workouts",
  "sleep",
  "steps",
  "weight",
  "resting_heart_rate",
  "heart_rate_summary",
] as const;
