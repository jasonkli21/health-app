export interface InsightsRequestIdentity {
  screenGeneration: number;
  requestGeneration: number;
  sessionEpoch: number;
  queryKey: string;
}

export type EvidenceReference = {
  object_id: string;
  revision: number;
  object_type: "derived_signal" | "event" | "observation";
};

export type EvidenceDestination =
  | {
      pathname: "/analytics/evidence/[objectId]";
      params: { objectId: string; revision: string };
    }
  | {
      pathname: "/daily/item/[itemId]/history";
      params: {
        itemId: string;
        type: "event" | "observation";
        revision: string;
      };
    };

export function isCurrentInsightsRequest(
  current: InsightsRequestIdentity,
  request: InsightsRequestIdentity,
): boolean {
  return (
    current.screenGeneration === request.screenGeneration &&
    current.requestGeneration === request.requestGeneration &&
    current.sessionEpoch === request.sessionEpoch &&
    current.queryKey === request.queryKey
  );
}

export function evidenceDestination(
  reference: EvidenceReference,
): EvidenceDestination {
  if (reference.object_type === "derived_signal") {
    return {
      pathname: "/analytics/evidence/[objectId]",
      params: {
        objectId: reference.object_id,
        revision: String(reference.revision),
      },
    };
  }
  return {
    pathname: "/daily/item/[itemId]/history",
    params: {
      itemId: reference.object_id,
      type: reference.object_type,
      revision: String(reference.revision),
    },
  };
}

export function formatInsightValue(value: number | null, unit: string): string {
  return value === null
    ? "No known values"
    : `${Number(value.toFixed(2))} ${unit}`;
}
