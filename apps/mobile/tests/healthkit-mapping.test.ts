import { describe, expect, it } from "vitest";

import {
  importResourceForSample,
  mapHeartRateSummary,
  mapSleep,
  mapSteps,
  mapWorkout,
  mapWeight,
  toImportEntry,
} from "../src/integrations/healthkit/mapping";
import { getHealthKitNativeCapability } from "../src/integrations/healthkit/nativeAdapter";
import type { HealthKitImportEntry } from "../src/integrations/healthkit/types";

function observationValue(record: HealthKitImportEntry["record"]): unknown {
  if (!("value" in record.payload)) throw new Error("Expected an Observation.");
  return record.payload.value;
}

describe("HealthKit normalization", () => {
  it("keeps native access disabled until the iOS adapter is verified", () => {
    expect(getHealthKitNativeCapability("ios")).toEqual({
      status: "native_adapter_unavailable",
    });
    expect(getHealthKitNativeCapability("android")).toEqual({
      status: "unsupported_platform",
    });
  });

  it("maps workouts to bounded Event records and prefers the elapsed interval", () => {
    const sample = mapWorkout({
      id: "1fbd7e9d-824d-4690-b529-ef64f93c3c55",
      startedAt: "2026-10-01T16:00:00Z",
      endedAt: "2026-10-01T16:45:00Z",
      timezone: "America/Los_Angeles",
      label: "Running",
      durationMinutes: 45,
      distanceMeters: 5000,
    });
    expect(sample.record).toMatchObject({
      domain: "exercise",
      ended_at: "2026-10-01T16:45:00Z",
      payload: { kind: "workout", label: "Running", distance: { value: 5000 } },
    });
    expect(sample.record).not.toHaveProperty("payload.duration");
    expect(importResourceForSample(sample)).toBe("workouts");
  });

  it("preserves sleep stage as allowlisted provenance metadata", () => {
    const sample = mapSleep({
      id: "d9e25fd1-8727-4bb6-9014-0fcb88c85db4",
      startedAt: "2026-10-01T07:00:00Z",
      endedAt: "2026-10-01T08:00:00Z",
      timezone: "America/Los_Angeles",
      stage: "deep",
    });
    expect(sample.metadata.sleep_stage).toBe("deep");
    expect(sample.record).toMatchObject({
      domain: "sleep",
      payload: { kind: "sleep" },
      ended_at: "2026-10-01T08:00:00Z",
    });
  });

  it("maps steps and heart-rate data as daily summaries without raw samples", () => {
    const steps = mapSteps({
      localDate: "2026-10-01",
      timezone: "America/Los_Angeles",
      installationId: "4bcf0eac-f815-4a88-bb6d-d10c477b8eab",
      count: 8000,
      methodVersion: "hk-steps-source-v1",
      sourceRevision: 1,
    });
    const heartRate = mapHeartRateSummary({
      localDate: "2026-10-01",
      timezone: "America/Los_Angeles",
      installationId: "4bcf0eac-f815-4a88-bb6d-d10c477b8eab",
      meanBpm: 71,
      minimumBpm: 52,
      maximumBpm: 116,
      sampleCount: 360,
      coverageStart: "2026-10-01T08:00:00Z",
      coverageEnd: "2026-10-01T22:00:00Z",
      methodVersion: "hk-heart-rate-v1",
      sourceRevision: 1,
    });
    expect(steps.sourceSampleId).toContain("daily:2026-10-01");
    expect(observationValue(steps.record)).toMatchObject({
      metric: "steps",
      value: 8000,
    });
    expect(heartRate.metadata).toMatchObject({
      aggregation_method_version: "hk-heart-rate-v1",
      sample_count: 360,
      minimum: 52,
      maximum: 116,
    });
    expect(JSON.stringify(toImportEntry(heartRate))).not.toContain(
      "raw_samples",
    );
  });

  it("rejects invalid or unbounded step aggregates before upload", () => {
    const aggregate = {
      localDate: "2026-10-01",
      timezone: "UTC",
      count: 10,
      installationId: "4bcf0eac-f815-4a88-bb6d-d10c477b8eab",
      methodVersion: "hk-steps-source-v1",
      sourceRevision: 1,
    };
    expect(() => mapSteps({ ...aggregate, count: Number.NaN })).toThrow(
      /bounded/,
    );
    expect(() => mapSteps({ ...aggregate, count: 1e301 })).toThrow(/bounded/);
  });

  it("maps weight to the original supported unit", () => {
    const sample = mapWeight({
      id: "4b7bf316-837d-4a7e-817f-5cf3d44f18ea",
      occurredAt: "2026-10-01T16:00:00Z",
      timezone: "America/Los_Angeles",
      value: 150,
      unit: "lb",
    });
    expect(observationValue(sample.record)).toMatchObject({
      metric: "weight",
      value: 150,
      unit: "lb",
    });
    expect(importResourceForSample(sample)).toBe("weight");
  });
});
