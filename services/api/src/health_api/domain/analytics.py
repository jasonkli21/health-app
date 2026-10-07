"""Versioned deterministic trend and association contracts for Phase 7."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from enum import StrEnum
from math import fsum, isfinite, sqrt
from statistics import median
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StrictInt, StrictStr, model_validator

from health_api.domain.schemas import StrictModel

TREND_METHOD_VERSION = "trend-v1"
ASSOCIATION_METHOD_VERSION = "spearman-sameday-v1"
INSIGHT_TEMPLATE_VERSION = "insight-template-v1"
MAX_ANALYSIS_DAYS = 366
MAX_ANALYSIS_ROWS = 10_000
MIN_COMPARISON_KNOWN_DAYS = 5
MIN_ASSOCIATION_PAIRED_DAYS = 14
MIN_ASSOCIATION_CALENDAR_DAYS = 21
MAX_ASSOCIATION_PAIRS = 5


class AnalyticsMetric(StrEnum):
    ENERGY = "energy"
    EXERCISE_DURATION = "exercise_duration"
    EXERCISE_DISTANCE = "exercise_distance"
    SLEEP_DURATION = "sleep_duration"
    SYMPTOM_SEVERITY = "symptom_severity"
    SYMPTOM_EPISODE_COUNT = "symptom_episode_count"
    WEIGHT = "weight"
    TEMPERATURE = "temperature"
    SYSTOLIC_PRESSURE = "systolic_pressure"
    DIASTOLIC_PRESSURE = "diastolic_pressure"
    PULSE = "pulse"


AnalysisMetricId = Annotated[
    StrictStr,
    Field(
        pattern=(
            r"^(energy|exercise_duration|exercise_distance|sleep_duration|symptom_severity|"
            r"symptom_episode_count|weight|temperature|systolic_pressure|diastolic_pressure|pulse|"
            r"tracker:[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}:"
            r"[a-z][a-z0-9_]{0,31}:v[1-9][0-9]*)$"
        )
    ),
]


class MetricDefinition(StrictModel):
    metric: AnalysisMetricId
    label: Annotated[StrictStr, Field(min_length=1, max_length=80)]
    unit: Annotated[StrictStr, Field(min_length=1, max_length=16)]
    aggregation: Annotated[StrictStr, Field(min_length=1, max_length=120)]
    minimum_known_days: Annotated[StrictInt, Field(ge=1)]


METRIC_CATALOG: dict[AnalyticsMetric, MetricDefinition] = {
    AnalyticsMetric.ENERGY: MetricDefinition(
        metric=AnalyticsMetric.ENERGY,
        label="Known meal energy subtotal",
        unit="kcal",
        aggregation="daily sum of reported meal energy; intake completeness is not inferred",
        minimum_known_days=5,
    ),
    AnalyticsMetric.EXERCISE_DURATION: MetricDefinition(
        metric=AnalyticsMetric.EXERCISE_DURATION,
        label="Exercise duration",
        unit="min",
        aggregation="daily sum of reported duration or elapsed interval overlap",
        minimum_known_days=5,
    ),
    AnalyticsMetric.EXERCISE_DISTANCE: MetricDefinition(
        metric=AnalyticsMetric.EXERCISE_DISTANCE,
        label="Exercise distance",
        unit="m",
        aggregation="daily sum attributed to workout start date",
        minimum_known_days=5,
    ),
    AnalyticsMetric.SLEEP_DURATION: MetricDefinition(
        metric=AnalyticsMetric.SLEEP_DURATION,
        label="Sleep duration",
        unit="min",
        aggregation="elapsed interval overlap per local calendar day",
        minimum_known_days=5,
    ),
    AnalyticsMetric.SYMPTOM_SEVERITY: MetricDefinition(
        metric=AnalyticsMetric.SYMPTOM_SEVERITY,
        label="Latest reported symptom severity",
        unit="score",
        aggregation="latest known linked or standalone severity per local date",
        minimum_known_days=5,
    ),
    AnalyticsMetric.SYMPTOM_EPISODE_COUNT: MetricDefinition(
        metric=AnalyticsMetric.SYMPTOM_EPISODE_COUNT,
        label="Reported symptom episodes",
        unit="episodes",
        aggregation="count of reported symptom events",
        minimum_known_days=5,
    ),
    AnalyticsMetric.WEIGHT: MetricDefinition(
        metric=AnalyticsMetric.WEIGHT,
        label="Latest weight",
        unit="kg",
        aggregation="latest known observation per local date",
        minimum_known_days=5,
    ),
    AnalyticsMetric.TEMPERATURE: MetricDefinition(
        metric=AnalyticsMetric.TEMPERATURE,
        label="Latest temperature",
        unit="C",
        aggregation="latest known observation per local date",
        minimum_known_days=5,
    ),
    AnalyticsMetric.SYSTOLIC_PRESSURE: MetricDefinition(
        metric=AnalyticsMetric.SYSTOLIC_PRESSURE,
        label="Latest systolic pressure",
        unit="mmHg",
        aggregation="latest known observation per local date",
        minimum_known_days=5,
    ),
    AnalyticsMetric.DIASTOLIC_PRESSURE: MetricDefinition(
        metric=AnalyticsMetric.DIASTOLIC_PRESSURE,
        label="Latest diastolic pressure",
        unit="mmHg",
        aggregation="latest known observation per local date",
        minimum_known_days=5,
    ),
    AnalyticsMetric.PULSE: MetricDefinition(
        metric=AnalyticsMetric.PULSE,
        label="Latest pulse",
        unit="bpm",
        aggregation="latest known observation per local date",
        minimum_known_days=5,
    ),
}


class AssociationPair(StrictModel):
    id: Annotated[StrictStr, Field(pattern=r"^[a-z_]+:[a-z_]+$")]
    first: AnalyticsMetric
    second: AnalyticsMetric
    lag_days: Literal[0] = 0


# The v1 set is deliberately small and fixed. Requests cannot invent pairs or
# enumerate every available combination.
ASSOCIATION_PAIRS: dict[str, AssociationPair] = {
    pair.id: pair
    for pair in (
        AssociationPair(
            id="sleep_duration:symptom_severity",
            first=AnalyticsMetric.SLEEP_DURATION,
            second=AnalyticsMetric.SYMPTOM_SEVERITY,
        ),
        AssociationPair(
            id="exercise_duration:sleep_duration",
            first=AnalyticsMetric.EXERCISE_DURATION,
            second=AnalyticsMetric.SLEEP_DURATION,
        ),
        AssociationPair(
            id="exercise_duration:symptom_episode_count",
            first=AnalyticsMetric.EXERCISE_DURATION,
            second=AnalyticsMetric.SYMPTOM_EPISODE_COUNT,
        ),
        AssociationPair(
            id="energy:symptom_severity",
            first=AnalyticsMetric.ENERGY,
            second=AnalyticsMetric.SYMPTOM_SEVERITY,
        ),
        AssociationPair(
            id="sleep_duration:pulse",
            first=AnalyticsMetric.SLEEP_DURATION,
            second=AnalyticsMetric.PULSE,
        ),
    )
}


class EvidenceReference(StrictModel):
    object_id: UUID
    revision: Annotated[int, Field(ge=1)]
    object_type: Literal["event", "observation"]


class DailyMetricPoint(StrictModel):
    date: date
    value: float | None
    logged_count: Annotated[int, Field(ge=0)]
    known_count: Annotated[int, Field(ge=0)]
    total_count: Annotated[int, Field(ge=0)]
    partial: bool


class RollingMeanPoint(StrictModel):
    date: date
    mean: float
    known_days: Literal[7] = 7


class PeriodSummary(StrictModel):
    from_date: date
    to_date: date
    known_days: Annotated[int, Field(ge=0)]
    mean: float | None
    median: float | None


class PeriodComparison(StrictModel):
    before: PeriodSummary
    after: PeriodSummary
    mean_difference: float | None
    percent_change: float | None


class TrendCoverage(StrictModel):
    calendar_days: Annotated[int, Field(ge=1, le=MAX_ANALYSIS_DAYS)]
    known_days: Annotated[int, Field(ge=0)]
    missing_days: Annotated[int, Field(ge=0)]
    logged_count: Annotated[int, Field(ge=0)]
    partial_days: Annotated[int, Field(ge=0)]


class TrendResult(StrictModel):
    method_version: Literal["trend-v1/unit-v1"]
    metric: AnalysisMetricId
    label: str
    unit: str
    from_date: date
    to_date: date
    timezone: Annotated[StrictStr, Field(min_length=1, max_length=64)]
    points: list[DailyMetricPoint] = Field(max_length=MAX_ANALYSIS_DAYS)
    coverage: TrendCoverage
    mean: float | None
    median: float | None
    rolling_7_known_day_mean: list[RollingMeanPoint] = Field(max_length=MAX_ANALYSIS_DAYS)
    comparison: PeriodComparison | None
    evidence_refs: list[EvidenceReference] = Field(max_length=MAX_ANALYSIS_ROWS)


class AssociationResult(StrictModel):
    method_version: Literal["spearman-sameday-v1"]
    pair: AssociationPair
    from_date: date
    to_date: date
    timezone: Annotated[StrictStr, Field(min_length=1, max_length=64)]
    status: Literal["available", "insufficient_data", "constant_series"]
    paired_days: Annotated[int, Field(ge=0)]
    calendar_days: Annotated[int, Field(ge=1, le=MAX_ANALYSIS_DAYS)]
    missing_pair_days: Annotated[int, Field(ge=0)]
    rho: float | None
    limitation: Literal["Association only; confounding and reporting bias are possible."] = (
        "Association only; confounding and reporting bias are possible."
    )
    evidence_refs: list[EvidenceReference] = Field(max_length=MAX_ANALYSIS_ROWS)


class InsightEvidenceReference(StrictModel):
    object_id: UUID
    revision: Annotated[int, Field(ge=1)]
    object_type: Literal["derived_signal", "event", "observation"]


class InsightPayloadV1(StrictModel):
    title: Annotated[StrictStr, Field(min_length=1, max_length=120)]
    explanation: Annotated[StrictStr, Field(min_length=1, max_length=1000)]
    kind: Literal["trend", "association", "coverage"]
    evidence_refs: list[InsightEvidenceReference] = Field(
        min_length=1, max_length=MAX_ANALYSIS_ROWS + 1
    )
    uncertainty: Annotated[StrictStr, Field(min_length=1, max_length=500)]
    method_version: Annotated[StrictStr, Field(min_length=1, max_length=80)]
    generated_by: Literal["deterministic"] = "deterministic"
    valid_from: datetime
    expires_at: datetime
    state: Literal["current", "stale", "dismissed", "expired"]

    @model_validator(mode="after")
    def validity_is_bounded(self) -> InsightPayloadV1:
        if (
            self.valid_from.tzinfo is None
            or self.valid_from.utcoffset() is None
            or self.expires_at.tzinfo is None
            or self.expires_at.utcoffset() is None
            or self.expires_at <= self.valid_from
            or self.expires_at - self.valid_from > timedelta(days=30)
        ):
            raise ValueError("insight expiry must be within 30 days")
        return self


class RecommendationPayloadV1(StrictModel):
    title: Annotated[StrictStr, Field(min_length=1, max_length=120)]
    suggestion: Annotated[StrictStr, Field(min_length=1, max_length=1000)]
    rationale: Annotated[StrictStr, Field(min_length=1, max_length=500)]
    risk_class: Literal["low"]
    evidence_refs: list[InsightEvidenceReference] = Field(
        min_length=1, max_length=MAX_ANALYSIS_ROWS + 1
    )
    expected_review_context: Annotated[StrictStr, Field(min_length=1, max_length=300)]
    generated_by: Literal["deterministic"] = "deterministic"
    created_at: datetime
    expires_at: datetime
    state: Literal["proposed", "accepted", "dismissed", "expired", "stale"]
    proposal_id: None = None

    @model_validator(mode="after")
    def expiry_is_bounded(self) -> RecommendationPayloadV1:
        if (
            self.created_at.tzinfo is None
            or self.created_at.utcoffset() is None
            or self.expires_at.tzinfo is None
            or self.expires_at.utcoffset() is None
            or self.expires_at <= self.created_at
            or self.expires_at - self.created_at > timedelta(days=30)
        ):
            raise ValueError("recommendation expiry must be within 30 days")
        return self


class ExperimentReference(StrictModel):
    object_id: UUID
    object_type: Literal["goal", "plan", "tracker_definition"]
    revision: Annotated[int, Field(ge=1)]


class ExperimentPayloadV1(StrictModel):
    hypothesis: Annotated[StrictStr, Field(min_length=1, max_length=2000)]
    intervention: Annotated[StrictStr, Field(min_length=1, max_length=2000)]
    linked_resource: ExperimentReference | None = None
    outcome_metric: AnalysisMetricId
    baseline_start: date
    start_date: date
    end_date: date
    status: Literal["draft", "active", "completed", "stopped", "archived"] = "draft"
    notes: Annotated[StrictStr, Field(max_length=2000)] = ""

    @model_validator(mode="after")
    def dates_are_ordered(self) -> ExperimentPayloadV1:
        if not self.baseline_start < self.start_date < self.end_date:
            raise ValueError("experiment baseline and intervention dates must be ordered")
        if (self.end_date - self.baseline_start).days + 1 > MAX_ANALYSIS_DAYS:
            raise ValueError("experiment window cannot exceed 366 days")
        return self


class ExperimentPeriodResult(StrictModel):
    from_date: date
    to_date: date
    known_days: Annotated[int, Field(ge=0)]
    missing_days: Annotated[int, Field(ge=0)]
    mean: float | None
    median: float | None


class ExperimentResult(StrictModel):
    metric: AnalysisMetricId
    unit: str
    timezone: Annotated[StrictStr, Field(min_length=1, max_length=64)]
    baseline: ExperimentPeriodResult
    intervention: ExperimentPeriodResult
    mean_difference: float | None
    method_version: Literal["experiment-descriptive-v1/unit-v1"]
    limitation: Literal["Descriptive comparison only; this does not establish causation."] = (
        "Descriptive comparison only; this does not establish causation."
    )
    evidence_refs: list[EvidenceReference] = Field(max_length=MAX_ANALYSIS_ROWS)


class AnalyticsError(StrictModel):
    code: Literal["range_too_large", "unsupported_metric", "invalid_pair", "insufficient_data"]
    message: Annotated[StrictStr, Field(min_length=1, max_length=240)]


def _period_summary(points: list[DailyMetricPoint], start: date, end: date) -> PeriodSummary:
    values = [
        point.value for point in points if start <= point.date <= end and point.value is not None
    ]
    return PeriodSummary(
        from_date=start,
        to_date=end,
        known_days=len(values),
        mean=fsum(values) / len(values) if values else None,
        median=median(values) if values else None,
    )


def build_trend_result(
    metric: str,
    points: list[DailyMetricPoint],
    *,
    definition: MetricDefinition,
    from_date: date,
    to_date: date,
    timezone: str,
    evidence_refs: list[EvidenceReference],
) -> TrendResult:
    """Build fixed descriptive summaries without filling missing days."""
    days = (to_date - from_date).days + 1
    if days < 1 or days > MAX_ANALYSIS_DAYS or len(points) != days:
        raise ValueError("analysis range is outside the supported bounds")
    known_points = [point for point in points if point.value is not None]
    known_values = [float(point.value) for point in known_points if point.value is not None]
    rolling: list[RollingMeanPoint] = []
    for index in range(6, len(known_points)):
        values = [
            float(point.value)
            for point in known_points[index - 6 : index + 1]
            if point.value is not None
        ]
        rolling.append(RollingMeanPoint(date=known_points[index].date, mean=fsum(values) / 7.0))

    comparison: PeriodComparison | None = None
    if days >= MIN_COMPARISON_KNOWN_DAYS * 2:
        split = from_date + timedelta(days=(days - 1) // 2)
        before = _period_summary(points, from_date, split)
        after_start = split + timedelta(days=1)
        after = _period_summary(points, after_start, to_date)
        if (
            before.known_days >= MIN_COMPARISON_KNOWN_DAYS
            and after.known_days >= MIN_COMPARISON_KNOWN_DAYS
            and before.mean is not None
            and after.mean is not None
        ):
            difference = after.mean - before.mean
            percent = (difference / before.mean * 100.0) if before.mean != 0.0 else None
            comparison = PeriodComparison(
                before=before,
                after=after,
                mean_difference=difference,
                percent_change=percent if percent is None or isfinite(percent) else None,
            )
    partial_days = sum(point.partial for point in points)
    return TrendResult(
        method_version="trend-v1/unit-v1",
        metric=metric,
        label=definition.label,
        unit=definition.unit,
        from_date=from_date,
        to_date=to_date,
        timezone=timezone,
        points=points,
        coverage=TrendCoverage(
            calendar_days=days,
            known_days=len(known_points),
            missing_days=days - len(known_points),
            logged_count=sum(point.logged_count for point in points),
            partial_days=partial_days,
        ),
        mean=fsum(known_values) / len(known_values) if known_values else None,
        median=median(known_values) if known_values else None,
        rolling_7_known_day_mean=rolling,
        comparison=comparison,
        evidence_refs=evidence_refs,
    )


def _average_ranks(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: (item[1], item[0]))
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(ordered):
        end = cursor + 1
        while end < len(ordered) and ordered[end][1] == ordered[cursor][1]:
            end += 1
        rank = (cursor + 1 + end) / 2.0
        for position in range(cursor, end):
            ranks[ordered[position][0]] = rank
        cursor = end
    return ranks


def spearman_rho(first: list[float], second: list[float]) -> float | None:
    """Spearman rank correlation with deterministic average ranks for ties."""
    if len(first) != len(second) or len(first) < 2:
        return None
    if any(not isfinite(value) for value in (*first, *second)):
        return None
    first_ranks = _average_ranks(first)
    second_ranks = _average_ranks(second)
    first_mean = fsum(first_ranks) / len(first_ranks)
    second_mean = fsum(second_ranks) / len(second_ranks)
    left = [value - first_mean for value in first_ranks]
    right = [value - second_mean for value in second_ranks]
    numerator = fsum(a * b for a, b in zip(left, right, strict=True))
    denominator = sqrt(
        fsum(value * value for value in left) * fsum(value * value for value in right)
    )
    if denominator == 0.0:
        return None
    result = numerator / denominator
    if not isfinite(result):
        return None
    return max(-1.0, min(1.0, result))


def build_association_result(
    pair: AssociationPair,
    first_points: list[DailyMetricPoint],
    second_points: list[DailyMetricPoint],
    *,
    from_date: date,
    to_date: date,
    timezone: str,
    evidence_refs: list[EvidenceReference],
) -> AssociationResult:
    if len(first_points) != len(second_points):
        raise ValueError("association series do not have aligned dates")
    if any(
        left.date != right.date for left, right in zip(first_points, second_points, strict=True)
    ):
        raise ValueError("association series do not have aligned dates")
    first: list[float] = []
    second: list[float] = []
    for left, right in zip(first_points, second_points, strict=True):
        if left.value is not None and right.value is not None:
            first.append(float(left.value))
            second.append(float(right.value))
    paired_days = len(first)
    span = (to_date - from_date).days + 1
    missing = span - paired_days
    if paired_days < MIN_ASSOCIATION_PAIRED_DAYS or span < MIN_ASSOCIATION_CALENDAR_DAYS:
        status: Literal["available", "insufficient_data", "constant_series"] = "insufficient_data"
        rho = None
    else:
        rho = spearman_rho(first, second)
        status = "constant_series" if rho is None else "available"
    return AssociationResult(
        method_version="spearman-sameday-v1",
        pair=pair,
        from_date=from_date,
        to_date=to_date,
        timezone=timezone,
        status=status,
        paired_days=paired_days,
        calendar_days=span,
        missing_pair_days=missing,
        rho=rho,
        evidence_refs=evidence_refs,
    )
