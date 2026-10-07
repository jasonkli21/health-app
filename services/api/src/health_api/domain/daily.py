"""Calendar-day and versioned unit rules shared by daily writes and Today reads."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from math import isfinite
from zoneinfo import ZoneInfo

from health_api.domain.schemas import (
    MAX_DAILY_QUANTITY,
    MeasurementUnit,
    MetricKey,
    validate_iana_timezone,
)

UNIT_CONVERSION_VERSION = "unit-v1"
TODAY_METHOD_VERSION = "today-v1"


def local_day_bounds(local_date: date, timezone: str) -> tuple[datetime, datetime]:
    """Return the half-open UTC interval for a local calendar day, including DST changes."""
    if local_date == date.max:
        raise ValueError("calendar day cannot be represented")
    zone_name = validate_iana_timezone(timezone)
    zone = ZoneInfo(zone_name)
    start = datetime.combine(local_date, time.min, tzinfo=zone).astimezone(UTC)
    end = datetime.combine(local_date + timedelta(days=1), time.min, tzinfo=zone).astimezone(UTC)
    return start, end


def interval_overlap_seconds(
    start: datetime,
    end: datetime,
    window_start: datetime,
    window_end: datetime,
) -> float:
    """Measure elapsed overlap between two aware half-open intervals."""
    if any(
        value.tzinfo is None or value.utcoffset() is None
        for value in (start, end, window_start, window_end)
    ):
        raise ValueError("interval bounds must be timezone-aware")
    overlap_start = max(start.astimezone(UTC), window_start.astimezone(UTC))
    overlap_end = min(end.astimezone(UTC), window_end.astimezone(UTC))
    return max(0.0, (overlap_end - overlap_start).total_seconds())


def canonical_unit(metric: MetricKey) -> MeasurementUnit:
    return {
        MetricKey.ENERGY: MeasurementUnit.KCAL,
        MetricKey.DURATION: MeasurementUnit.MIN,
        MetricKey.DISTANCE: MeasurementUnit.M,
        MetricKey.WEIGHT: MeasurementUnit.KG,
        MetricKey.TEMPERATURE: MeasurementUnit.CELSIUS,
        MetricKey.SYSTOLIC_PRESSURE: MeasurementUnit.MMHG,
        MetricKey.DIASTOLIC_PRESSURE: MeasurementUnit.MMHG,
        MetricKey.PULSE: MeasurementUnit.BPM,
        MetricKey.STEPS: MeasurementUnit.STEPS,
        MetricKey.RESTING_HEART_RATE: MeasurementUnit.BPM,
        MetricKey.HEART_RATE_SUMMARY: MeasurementUnit.BPM,
        MetricKey.SYMPTOM_SEVERITY: MeasurementUnit.SCORE,
        MetricKey.SYMPTOM_EPISODE_COUNT: MeasurementUnit.EPISODES,
    }[metric]


def convert_value(
    metric: MetricKey,
    value: float,
    from_unit: MeasurementUnit,
    to_unit: MeasurementUnit | None = None,
) -> float:
    """Convert supported daily quantities using the immutable unit-v1 factors."""
    target = to_unit or canonical_unit(metric)
    if not isfinite(value):
        raise ValueError("quantity must be finite")
    if abs(value) > MAX_DAILY_QUANTITY:
        raise ValueError("quantity is outside the safe numeric range")
    supported = {
        MetricKey.ENERGY: {MeasurementUnit.KCAL, MeasurementUnit.KJ},
        MetricKey.DURATION: {MeasurementUnit.MIN, MeasurementUnit.HOUR},
        MetricKey.DISTANCE: {MeasurementUnit.M, MeasurementUnit.KM, MeasurementUnit.MI},
        MetricKey.WEIGHT: {MeasurementUnit.KG, MeasurementUnit.LB},
        MetricKey.TEMPERATURE: {MeasurementUnit.CELSIUS, MeasurementUnit.FAHRENHEIT},
        MetricKey.SYSTOLIC_PRESSURE: {MeasurementUnit.MMHG},
        MetricKey.DIASTOLIC_PRESSURE: {MeasurementUnit.MMHG},
        MetricKey.PULSE: {MeasurementUnit.BPM},
        MetricKey.STEPS: {MeasurementUnit.STEPS},
        MetricKey.RESTING_HEART_RATE: {MeasurementUnit.BPM},
        MetricKey.HEART_RATE_SUMMARY: {MeasurementUnit.BPM},
        MetricKey.SYMPTOM_SEVERITY: {MeasurementUnit.SCORE},
        MetricKey.SYMPTOM_EPISODE_COUNT: {MeasurementUnit.EPISODES},
    }
    if from_unit not in supported[metric] or target not in supported[metric]:
        raise ValueError("unit is not supported for this metric")
    if from_unit == target:
        return value

    if metric == MetricKey.TEMPERATURE:
        if from_unit == MeasurementUnit.FAHRENHEIT:
            value = (value - 32.0) * (5.0 / 9.0)
        if target == MeasurementUnit.FAHRENHEIT:
            value = value * (9.0 / 5.0) + 32.0
        if not isfinite(value) or abs(value) > MAX_DAILY_QUANTITY:
            raise ValueError("converted quantity is outside the supported numeric range")
        return value

    to_base_factor = {
        (MetricKey.ENERGY, MeasurementUnit.KJ): 1.0 / 4.184,
        (MetricKey.DURATION, MeasurementUnit.HOUR): 60.0,
        (MetricKey.DISTANCE, MeasurementUnit.KM): 1000.0,
        (MetricKey.DISTANCE, MeasurementUnit.MI): 1609.344,
        (MetricKey.WEIGHT, MeasurementUnit.LB): 0.45359237,
    }
    from_base_factor = {
        (MetricKey.ENERGY, MeasurementUnit.KJ): 4.184,
        (MetricKey.DURATION, MeasurementUnit.HOUR): 1.0 / 60.0,
        (MetricKey.DISTANCE, MeasurementUnit.KM): 1.0 / 1000.0,
        (MetricKey.DISTANCE, MeasurementUnit.MI): 1.0 / 1609.344,
        (MetricKey.WEIGHT, MeasurementUnit.LB): 1.0 / 0.45359237,
    }
    base_value = value * to_base_factor.get((metric, from_unit), 1.0)
    converted = base_value * from_base_factor.get((metric, target), 1.0)
    if not isfinite(converted) or abs(converted) > MAX_DAILY_QUANTITY:
        raise ValueError("converted quantity is outside the supported numeric range")
    return converted
