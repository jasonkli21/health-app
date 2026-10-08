"""Stable application façade for planning resources and schedules.

Resource revisions live in ``planning_resources``; schedule and occurrence
transactions live in ``planning_schedules``. Keep routes and established
imports on this module while use cases remain separated internally.
"""

from health_api.application.planning_resources import (
    PlanningAggregate,
    PlanningKind,
    PlanningPayload,
    _canonical,
    _link_specs,
    _payload,
    _sync_links,
    _validate_references,
    archive_planning_resource,
    create_planning_resource,
    get_planning_resource,
    list_planning_history,
    list_planning_resources,
    reorder_plan_items,
    transition_planning_resource,
    update_planning_resource,
)
from health_api.application.planning_schedules import (
    _occurrence_is_eligible,
    _parse_schedule_key,
    _recorded_occurrence_details,
    _schedule_key,
    _schedule_row_for_date,
    get_planning_schedule,
    list_occurrence_history,
    list_planning_occurrences,
    load_today_planning,
    record_occurrence_action,
    set_planning_schedule,
)

__all__ = [
    "PlanningAggregate",
    "PlanningKind",
    "PlanningPayload",
    "_canonical",
    "_link_specs",
    "_occurrence_is_eligible",
    "_parse_schedule_key",
    "_payload",
    "_recorded_occurrence_details",
    "_schedule_key",
    "_schedule_row_for_date",
    "_sync_links",
    "_validate_references",
    "archive_planning_resource",
    "create_planning_resource",
    "get_planning_resource",
    "get_planning_schedule",
    "list_occurrence_history",
    "list_planning_history",
    "list_planning_occurrences",
    "list_planning_resources",
    "load_today_planning",
    "record_occurrence_action",
    "reorder_plan_items",
    "set_planning_schedule",
    "transition_planning_resource",
    "update_planning_resource",
]
