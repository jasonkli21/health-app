import type { PlanningItem } from "./api";

function payload(item: PlanningItem): unknown {
  switch (item.object_type) {
    case "goal":
      return item.goal;
    case "regimen":
      return item.regimen;
    case "plan":
      return item.plan;
    case "context":
      return item.context;
    case "tracker_definition":
      return item.definition;
  }
}

// Schedule-only revisions can advance without replacing an in-memory draft.
// Content or permission changes need an explicit reload before a full update;
// otherwise the old form silently overwrites someone else's newer fields.
export function canAdvancePlanningRevision(
  baseline: PlanningItem,
  incoming: PlanningItem,
): boolean {
  return (
    baseline.id === incoming.id &&
    baseline.object_type === incoming.object_type &&
    baseline.notes === incoming.notes &&
    baseline.status === incoming.status &&
    baseline.lifecycle === incoming.lifecycle &&
    baseline.ai_use_allowed === incoming.ai_use_allowed &&
    baseline.cross_domain_use_allowed === incoming.cross_domain_use_allowed &&
    JSON.stringify(payload(baseline)) === JSON.stringify(payload(incoming))
  );
}
