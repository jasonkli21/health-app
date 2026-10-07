import type {
  HealthKitImportEntry,
  HealthKitImportMetadata,
  HealthKitResourceType,
  NormalizedHealthSample,
} from "./types";

type SourceDetails = {
  sourceBundleIdentifier?: string;
  deviceLabel?: string;
};

type WorkoutSample = SourceDetails & {
  id: string;
  startedAt: string;
  endedAt?: string;
  timezone: string;
  label: string;
  durationMinutes?: number;
  distanceMeters?: number;
};

type SleepSample = SourceDetails & {
  id: string;
  startedAt: string;
  endedAt: string;
  timezone: string;
  stage?: NonNullable<HealthKitImportMetadata["sleep_stage"]>;
};

type WeightSample = SourceDetails & {
  id: string;
  occurredAt: string;
  timezone: string;
  value: number;
  unit: "kg" | "lb";
};

type RestingHeartRateSample = SourceDetails & {
  id: string;
  occurredAt: string;
  timezone: string;
  beatsPerMinute: number;
};

type StepsAggregate = SourceDetails & {
  localDate: string;
  timezone: string;
  count: number;
  installationId: string;
  methodVersion: string;
  sampleCount?: number;
};

type HeartRateSummary = SourceDetails & {
  localDate: string;
  timezone: string;
  installationId: string;
  meanBpm: number;
  minimumBpm: number;
  maximumBpm: number;
  sampleCount: number;
  coverageStart: string;
  coverageEnd: string;
  methodVersion: string;
};

function sourceMetadata(source: SourceDetails): HealthKitImportMetadata {
  return {
    ...(source.sourceBundleIdentifier
      ? { source_bundle_identifier: source.sourceBundleIdentifier }
      : {}),
    ...(source.deviceLabel ? { device_label: source.deviceLabel } : {}),
  };
}

function dailyAggregateId(
  localDate: string,
  timezone: string,
  installationId: string,
): string {
  return `daily:${localDate}:${timezone}:healthkit-v1:${installationId}`;
}

export function mapWorkout(sample: WorkoutSample): NormalizedHealthSample {
  const hasEnd = sample.endedAt !== undefined;
  const duration = hasEnd ? undefined : sample.durationMinutes;
  return {
    sourceSampleId: sample.id,
    record: {
      domain: "exercise",
      time: {
        precision: "instant",
        occurred_at: sample.startedAt,
        timezone: sample.timezone,
      },
      ended_at: sample.endedAt ?? null,
      payload: {
        kind: "workout",
        label: sample.label,
        ...(duration === undefined
          ? {}
          : { duration: { value: duration, unit: "min" } }),
        ...(sample.distanceMeters === undefined
          ? {}
          : { distance: { value: sample.distanceMeters, unit: "m" } }),
      },
      notes: null,
    },
    metadata: sourceMetadata(sample),
  };
}

export function mapSleep(sample: SleepSample): NormalizedHealthSample {
  return {
    sourceSampleId: sample.id,
    record: {
      domain: "sleep",
      time: {
        precision: "instant",
        occurred_at: sample.startedAt,
        timezone: sample.timezone,
      },
      ended_at: sample.endedAt,
      payload: { kind: "sleep", label: "Sleep" },
      notes: null,
    },
    metadata: {
      ...sourceMetadata(sample),
      ...(sample.stage ? { sleep_stage: sample.stage } : {}),
    },
  };
}

export function mapWeight(sample: WeightSample): NormalizedHealthSample {
  return {
    sourceSampleId: sample.id,
    record: {
      domain: "measurements",
      time: {
        precision: "instant",
        occurred_at: sample.occurredAt,
        timezone: sample.timezone,
      },
      interval_end: null,
      payload: {
        value: { metric: "weight", value: sample.value, unit: sample.unit },
      },
      notes: null,
    },
    metadata: sourceMetadata(sample),
  };
}

export function mapRestingHeartRate(
  sample: RestingHeartRateSample,
): NormalizedHealthSample {
  return {
    sourceSampleId: sample.id,
    record: {
      domain: "measurements",
      time: {
        precision: "instant",
        occurred_at: sample.occurredAt,
        timezone: sample.timezone,
      },
      interval_end: null,
      payload: {
        value: {
          metric: "resting_heart_rate",
          value: sample.beatsPerMinute,
          unit: "bpm",
        },
      },
      notes: null,
    },
    metadata: sourceMetadata(sample),
  };
}

export function mapSteps(aggregate: StepsAggregate): NormalizedHealthSample {
  return {
    sourceSampleId: dailyAggregateId(
      aggregate.localDate,
      aggregate.timezone,
      aggregate.installationId,
    ),
    record: {
      domain: "exercise",
      time: {
        precision: "date_only",
        local_date: aggregate.localDate,
        timezone: aggregate.timezone,
      },
      interval_end: null,
      payload: {
        value: { metric: "steps", value: aggregate.count, unit: "steps" },
      },
      notes: null,
    },
    metadata: {
      ...sourceMetadata(aggregate),
      aggregation_method_version: aggregate.methodVersion,
      ...(aggregate.sampleCount === undefined
        ? {}
        : { sample_count: aggregate.sampleCount }),
    },
  };
}

export function mapHeartRateSummary(
  aggregate: HeartRateSummary,
): NormalizedHealthSample {
  return {
    sourceSampleId: dailyAggregateId(
      aggregate.localDate,
      aggregate.timezone,
      aggregate.installationId,
    ),
    record: {
      domain: "measurements",
      time: {
        precision: "date_only",
        local_date: aggregate.localDate,
        timezone: aggregate.timezone,
      },
      interval_end: null,
      payload: {
        value: {
          metric: "heart_rate_summary",
          value: aggregate.meanBpm,
          unit: "bpm",
        },
      },
      notes: null,
    },
    metadata: {
      ...sourceMetadata(aggregate),
      aggregation_method_version: aggregate.methodVersion,
      sample_count: aggregate.sampleCount,
      minimum: aggregate.minimumBpm,
      maximum: aggregate.maximumBpm,
      coverage_start: aggregate.coverageStart,
      coverage_end: aggregate.coverageEnd,
    },
  };
}

export function importResourceForSample(
  sample: NormalizedHealthSample,
): HealthKitResourceType {
  if ("kind" in sample.record.payload) {
    if (sample.record.payload.kind === "sleep") return "sleep";
    if (sample.record.payload.kind === "workout") return "workouts";
    throw new Error(
      "Sample does not map to a supported HealthKit import type.",
    );
  }
  if (!("value" in sample.record.payload)) {
    throw new Error(
      "Sample does not map to a supported HealthKit import type.",
    );
  }
  const value = sample.record.payload.value;
  if (value.metric === "steps") return "steps";
  if (value.metric === "weight") return "weight";
  if (value.metric === "resting_heart_rate") return "resting_heart_rate";
  if (value.metric === "heart_rate_summary") return "heart_rate_summary";
  throw new Error("Sample does not map to a supported HealthKit import type.");
}

export function toImportEntry(
  sample: NormalizedHealthSample,
): HealthKitImportEntry {
  return {
    source_sample_id: sample.sourceSampleId,
    record: sample.record,
    metadata: sample.metadata,
  };
}
