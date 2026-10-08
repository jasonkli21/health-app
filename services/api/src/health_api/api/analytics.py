"""Owner-scoped deterministic trends, insights, recommendations, and experiments."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Response
from health_api.api.dependencies import get_current_owner, get_session
from health_api.api.errors import APIError
from health_api.api.schemas import (
    AnalyticsAssociationCatalogResponse,
    AnalyticsHistoryEntry,
    AnalyticsMetricCatalogResponse,
    ErrorResponse,
    ExperimentCreateRequest,
    ExperimentListResponse,
    ExperimentResponse,
    ExperimentResultResponse,
    ExperimentStateRequest,
    ExperimentUpdateRequest,
    InsightGenerateRequest,
    InsightGenerateResponse,
    InsightListResponse,
    InsightResponse,
    InsightStateRequest,
    RecommendationListResponse,
    RecommendationResponse,
    RecommendationStateRequest,
    StoredAssociationResponse,
    StoredTrendResponse,
)
from health_api.application.analytics_service import (
    AnalyticsNotFound,
    ArtifactAggregate,
    StoredSignal,
    change_insight_state,
    change_recommendation_state,
    compute_associations,
    compute_trend,
    create_experiment,
    experiment_result,
    expire_artifact_for_response,
    generate_insights,
    list_artifacts,
    list_metric_definitions,
    transition_experiment,
    update_experiment,
)
from health_api.application.today_service import owner_today_settings
from health_api.domain.analytics import (
    ASSOCIATION_PAIRS,
    AssociationResult,
    ExperimentPayloadV1,
    InsightPayloadV1,
    RecommendationPayloadV1,
    TrendResult,
)
from health_api.domain.schemas import validate_iana_timezone
from health_api.persistence.models import AnalyticsArtifact, HealthObject, HealthObjectRevision
from pydantic import ValidationError
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

router = APIRouter(tags=["analytics"])

COMMON_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Authentication is required or invalid."},
    404: {"model": ErrorResponse, "description": "The owner-scoped analytics item was not found."},
    409: {
        "model": ErrorResponse,
        "description": "The analytics item changed or its state conflicts.",
    },
    413: {"model": ErrorResponse, "description": "Request body exceeds the 65,536 byte limit."},
    422: {
        "model": ErrorResponse,
        "description": "The analytics request is invalid or exceeds its bounds.",
    },
    503: {"model": ErrorResponse, "description": "Health storage is unavailable."},
}


@router.get(
    "/analytics/artifacts/{artifact_id}/history/{revision}",
    response_model=AnalyticsHistoryEntry,
    operation_id="getAnalyticsHistory",
    responses=COMMON_ERRORS,
)
def get_analytics_history(
    artifact_id: UUID,
    revision: Annotated[int, Path(ge=1)],
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> AnalyticsHistoryEntry:
    row = session.execute(
        select(HealthObjectRevision)
        .join(
            AnalyticsArtifact,
            and_(
                AnalyticsArtifact.owner_id == HealthObjectRevision.owner_id,
                AnalyticsArtifact.object_id == HealthObjectRevision.object_id,
            ),
        )
        .where(
            HealthObjectRevision.owner_id == owner_id,
            HealthObjectRevision.object_id == artifact_id,
            HealthObjectRevision.revision == revision,
            AnalyticsArtifact.artifact_kind.in_(
                ("derived_signal", "insight", "recommendation", "experiment")
            ),
        )
    ).scalar_one_or_none()
    if row is None:
        raise AnalyticsNotFound
    return AnalyticsHistoryEntry(
        object_id=row.object_id,
        revision=row.revision,
        recorded_at=row.recorded_at,
        snapshot=row.snapshot,
    )


def _owner_binding(owner_id: UUID) -> str:
    return hashlib.sha256(owner_id.bytes).hexdigest()


def _encode_cursor(
    owner_id: UUID,
    kind: str,
    state: str | None,
    item: ArtifactAggregate,
) -> str:
    obj, _ = item
    payload = {
        "v": 1,
        "owner": _owner_binding(owner_id),
        "kind": kind,
        "state": state,
        "created_at": obj.created_at.astimezone(UTC).isoformat(),
        "id": str(obj.id),
    }
    return (
        base64.urlsafe_b64encode(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        .decode("ascii")
        .rstrip("=")
    )


def _decode_cursor(
    value: str, owner_id: UUID, kind: str, state: str | None
) -> tuple[datetime, UUID]:
    try:
        if len(value) > 2048:
            raise ValueError
        payload = json.loads(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))
        if not isinstance(payload, dict) or set(payload) != {
            "v",
            "owner",
            "kind",
            "state",
            "created_at",
            "id",
        }:
            raise ValueError
        if (
            payload["v"] != 1
            or payload["owner"] != _owner_binding(owner_id)
            or payload["kind"] != kind
            or payload["state"] != state
        ):
            raise ValueError
        created_at = datetime.fromisoformat(payload["created_at"])
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError
        return created_at.astimezone(UTC), UUID(payload["id"])
    except (ValueError, TypeError, KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise APIError(
            422, "invalid_cursor", "Pagination cursor is invalid for these filters."
        ) from exc


def _range_timezone(
    owner_id: UUID,
    session: Session,
    from_date: date,
    to_date: date,
    requested_timezone: str | None,
) -> str:
    _, owner_timezone = owner_today_settings(session, owner_id)
    try:
        timezone = validate_iana_timezone(requested_timezone or owner_timezone)
    except ValueError as exc:
        raise APIError(422, "invalid_timezone", "Timezone must be a valid IANA name.") from exc
    days = (to_date - from_date).days + 1
    if from_date > to_date or days > 366 or to_date >= date.max - timedelta(days=1):
        raise APIError(422, "range_too_large", "Choose a valid date range of at most 366 days.")
    return timezone


def _stored_trend(signal: StoredSignal) -> StoredTrendResponse:
    if not isinstance(signal.result, TrendResult):
        raise TypeError("trend operation returned a non-trend signal")
    return StoredTrendResponse(
        id=signal.obj.id,
        revision=signal.obj.revision,
        state=cast(Literal["current", "stale"], signal.artifact.state),
        result=signal.result,
    )


def _stored_association(signal: StoredSignal) -> StoredAssociationResponse:
    if not isinstance(signal.result, AssociationResult):
        raise TypeError("association operation returned a non-association signal")
    return StoredAssociationResponse(
        id=signal.obj.id,
        revision=signal.obj.revision,
        state=cast(Literal["current", "stale"], signal.artifact.state),
        result=signal.result,
    )


def _insight_response(session: Session, owner_id: UUID, item: ArtifactAggregate) -> InsightResponse:
    obj, artifact = item
    obj, artifact = expire_artifact_for_response(
        session, owner_id, obj, artifact, datetime.now(UTC)
    )
    try:
        payload = InsightPayloadV1.model_validate(artifact.payload)
    except ValidationError as exc:
        raise RuntimeError("stored insight schema is invalid") from exc
    return InsightResponse(
        id=obj.id,
        revision=obj.revision,
        title=obj.title,
        state=cast(Literal["current", "stale", "dismissed", "expired"], artifact.state),
        created_at=obj.created_at,
        updated_at=obj.updated_at,
        insight=payload,
    )


def _recommendation_response(
    session: Session, owner_id: UUID, item: ArtifactAggregate
) -> RecommendationResponse:
    obj, artifact = item
    obj, artifact = expire_artifact_for_response(
        session, owner_id, obj, artifact, datetime.now(UTC)
    )
    try:
        payload = RecommendationPayloadV1.model_validate(artifact.payload)
    except ValidationError as exc:
        raise RuntimeError("stored recommendation schema is invalid") from exc
    return RecommendationResponse(
        id=obj.id,
        revision=obj.revision,
        title=obj.title,
        state=cast(
            Literal["proposed", "accepted", "dismissed", "expired", "stale"], artifact.state
        ),
        created_at=obj.created_at,
        updated_at=obj.updated_at,
        recommendation=payload,
    )


def _experiment_response(item: ArtifactAggregate) -> ExperimentResponse:
    obj, artifact = item
    try:
        payload = ExperimentPayloadV1.model_validate(artifact.payload)
    except ValidationError as exc:
        raise RuntimeError("stored experiment schema is invalid") from exc
    return ExperimentResponse(
        id=obj.id,
        revision=obj.revision,
        title=obj.title,
        state=cast(Literal["draft", "active", "completed", "stopped", "archived"], artifact.state),
        created_at=obj.created_at,
        updated_at=obj.updated_at,
        experiment=payload,
    )


def _list_artifacts(
    session: Session,
    owner_id: UUID,
    kind: Literal["insight", "recommendation", "experiment"],
    limit: int,
    state: str | None,
    cursor: str | None,
) -> tuple[list[ArtifactAggregate], str | None]:
    after = _decode_cursor(cursor, owner_id, kind, state) if cursor else None
    page = list_artifacts(session, owner_id, kind, state=state, limit=limit + 1, after=after)
    has_more = len(page) > limit
    page = page[:limit]
    next_cursor = _encode_cursor(owner_id, kind, state, page[-1]) if has_more and page else None
    return page, next_cursor


@router.get(
    "/analytics/catalog",
    response_model=AnalyticsMetricCatalogResponse,
    operation_id="listAnalyticsMetrics",
    responses=COMMON_ERRORS,
)
def analytics_catalog(
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> AnalyticsMetricCatalogResponse:
    return AnalyticsMetricCatalogResponse(items=list_metric_definitions(session, owner_id))


@router.get(
    "/analytics/associations/catalog",
    response_model=AnalyticsAssociationCatalogResponse,
    operation_id="listAnalyticsAssociationPairs",
    responses=COMMON_ERRORS,
)
def association_catalog(
    _owner_id: Annotated[UUID, Depends(get_current_owner)],
) -> AnalyticsAssociationCatalogResponse:
    return AnalyticsAssociationCatalogResponse(items=list(ASSOCIATION_PAIRS.values()))


@router.get(
    "/trends",
    response_model=StoredTrendResponse,
    operation_id="getTrend",
    responses=COMMON_ERRORS,
)
def get_trend(
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    metric: Annotated[str, Query(min_length=1, max_length=128)],
    from_date: Annotated[date, Query(alias="from")],
    to_date: Annotated[date, Query(alias="to")],
    timezone: Annotated[str | None, Query(max_length=64)] = None,
) -> StoredTrendResponse:
    effective_timezone = _range_timezone(owner_id, session, from_date, to_date, timezone)
    return _stored_trend(
        compute_trend(session, owner_id, metric, from_date, to_date, effective_timezone)
    )


@router.get(
    "/associations",
    response_model=list[StoredAssociationResponse],
    operation_id="getAssociations",
    responses=COMMON_ERRORS,
)
def get_associations(
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    pair: Annotated[list[str], Query(min_length=1, max_length=5)],
    from_date: Annotated[date, Query(alias="from")],
    to_date: Annotated[date, Query(alias="to")],
    timezone: Annotated[str | None, Query(max_length=64)] = None,
) -> list[StoredAssociationResponse]:
    effective_timezone = _range_timezone(owner_id, session, from_date, to_date, timezone)
    signals = compute_associations(session, owner_id, pair, from_date, to_date, effective_timezone)
    return [_stored_association(signal) for signal in signals]


@router.post(
    "/insights/refresh",
    response_model=InsightGenerateResponse,
    status_code=201,
    operation_id="refreshInsights",
    responses=COMMON_ERRORS,
)
def refresh_insights(
    body: InsightGenerateRequest,
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> InsightGenerateResponse:
    effective_timezone = _range_timezone(
        owner_id, session, body.from_date, body.to_date, body.timezone
    )
    signals, generated = generate_insights(
        session,
        owner_id,
        list(body.metrics),
        list(body.association_pairs),
        body.from_date,
        body.to_date,
        effective_timezone,
    )
    insights: list[InsightResponse] = []
    recommendations: list[RecommendationResponse] = []
    for item in generated:
        if item[1].artifact_kind == "insight":
            insights.append(_insight_response(session, owner_id, item))
        elif item[1].artifact_kind == "recommendation":
            recommendations.append(_recommendation_response(session, owner_id, item))
    return InsightGenerateResponse(
        signals=[
            _stored_trend(signal) for signal in signals if isinstance(signal.result, TrendResult)
        ],
        associations=[
            _stored_association(signal)
            for signal in signals
            if not isinstance(signal.result, TrendResult)
        ],
        insights=insights,
        recommendations=recommendations,
    )


@router.get(
    "/insights",
    response_model=InsightListResponse,
    operation_id="listInsights",
    responses=COMMON_ERRORS,
)
def get_insights(
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    state: Annotated[Literal["current", "stale", "dismissed", "expired"] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
) -> InsightListResponse:
    page, next_cursor = _list_artifacts(session, owner_id, "insight", limit, state, cursor)
    return InsightListResponse(
        items=[_insight_response(session, owner_id, item) for item in page], next_cursor=next_cursor
    )


@router.get(
    "/insights/{insight_id}",
    response_model=InsightResponse,
    operation_id="getInsight",
    responses=COMMON_ERRORS,
)
def get_insight(
    insight_id: UUID,
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> InsightResponse:
    from health_api.application.analytics_service import _artifact_aggregate

    return _insight_response(
        session, owner_id, _artifact_aggregate(session, owner_id, insight_id, "insight")
    )


@router.patch(
    "/insights/{insight_id}/state",
    response_model=InsightResponse,
    operation_id="changeInsightState",
    responses=COMMON_ERRORS,
)
def patch_insight_state(
    insight_id: UUID,
    body: InsightStateRequest,
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> InsightResponse:
    item = change_insight_state(session, owner_id, insight_id, body.expected_revision, body.state)
    return _insight_response(session, owner_id, item)


@router.get(
    "/recommendations",
    response_model=RecommendationListResponse,
    operation_id="listRecommendations",
    responses=COMMON_ERRORS,
)
def get_recommendations(
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    state: Annotated[
        Literal["proposed", "accepted", "dismissed", "expired", "stale"] | None, Query()
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
) -> RecommendationListResponse:
    page, next_cursor = _list_artifacts(session, owner_id, "recommendation", limit, state, cursor)
    return RecommendationListResponse(
        items=[_recommendation_response(session, owner_id, item) for item in page],
        next_cursor=next_cursor,
    )


@router.get(
    "/recommendations/{recommendation_id}",
    response_model=RecommendationResponse,
    operation_id="getRecommendation",
    responses=COMMON_ERRORS,
)
def get_recommendation(
    recommendation_id: UUID,
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> RecommendationResponse:
    from health_api.application.analytics_service import _artifact_aggregate

    return _recommendation_response(
        session,
        owner_id,
        _artifact_aggregate(session, owner_id, recommendation_id, "recommendation"),
    )


@router.patch(
    "/recommendations/{recommendation_id}/state",
    response_model=RecommendationResponse,
    operation_id="changeRecommendationState",
    responses=COMMON_ERRORS,
)
def patch_recommendation_state(
    recommendation_id: UUID,
    body: RecommendationStateRequest,
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> RecommendationResponse:
    item = change_recommendation_state(
        session, owner_id, recommendation_id, body.expected_revision, body.state
    )
    return _recommendation_response(session, owner_id, item)


@router.get(
    "/experiments",
    response_model=ExperimentListResponse,
    operation_id="listExperiments",
    responses=COMMON_ERRORS,
)
def get_experiments(
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    state: Annotated[
        Literal["draft", "active", "completed", "stopped", "archived"] | None, Query()
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
) -> ExperimentListResponse:
    page, next_cursor = _list_artifacts(session, owner_id, "experiment", limit, state, cursor)
    return ExperimentListResponse(
        items=[_experiment_response(item) for item in page], next_cursor=next_cursor
    )


@router.post(
    "/experiments",
    response_model=ExperimentResponse,
    status_code=201,
    operation_id="createExperiment",
    responses=COMMON_ERRORS,
)
def post_experiment(
    body: ExperimentCreateRequest,
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    response: Response,
) -> ExperimentResponse:
    existing = session.scalar(
        select(HealthObject.id).where(
            HealthObject.owner_id == owner_id,
            HealthObject.id == body.id,
            HealthObject.object_type == "experiment",
        )
    )
    item = create_experiment(session, owner_id, body.id, body.experiment)
    if existing is not None:
        response.status_code = 200
    return _experiment_response(item)


@router.get(
    "/experiments/{experiment_id}",
    response_model=ExperimentResponse,
    operation_id="getExperiment",
    responses=COMMON_ERRORS,
)
def get_experiment(
    experiment_id: UUID,
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> ExperimentResponse:
    from health_api.application.analytics_service import _artifact_aggregate

    return _experiment_response(_artifact_aggregate(session, owner_id, experiment_id, "experiment"))


@router.patch(
    "/experiments/{experiment_id}",
    response_model=ExperimentResponse,
    operation_id="updateExperiment",
    responses=COMMON_ERRORS,
)
def patch_experiment(
    experiment_id: UUID,
    body: ExperimentUpdateRequest,
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> ExperimentResponse:
    return _experiment_response(
        update_experiment(session, owner_id, experiment_id, body.expected_revision, body.experiment)
    )


@router.patch(
    "/experiments/{experiment_id}/state",
    response_model=ExperimentResponse,
    operation_id="changeExperimentState",
    responses=COMMON_ERRORS,
)
def patch_experiment_state(
    experiment_id: UUID,
    body: ExperimentStateRequest,
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> ExperimentResponse:
    return _experiment_response(
        transition_experiment(session, owner_id, experiment_id, body.expected_revision, body.state)
    )


@router.get(
    "/experiments/{experiment_id}/results",
    response_model=ExperimentResultResponse,
    operation_id="getExperimentResults",
    responses=COMMON_ERRORS,
)
def get_experiment_results(
    experiment_id: UUID,
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    timezone: Annotated[str | None, Query(max_length=64)] = None,
) -> ExperimentResultResponse:
    _, owner_timezone = owner_today_settings(session, owner_id)
    try:
        effective_timezone = validate_iana_timezone(timezone or owner_timezone)
    except ValueError as exc:
        raise APIError(422, "invalid_timezone", "Timezone must be a valid IANA name.") from exc
    item, result = experiment_result(session, owner_id, experiment_id, effective_timezone)
    return ExperimentResultResponse(experiment=_experiment_response(item), result=result)
