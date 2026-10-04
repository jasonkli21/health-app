import type { components } from "@personal-health/api-client";

type TodayResponse = components["schemas"]["TodayResponse"];

export type TodaySnapshotIdentity = {
  scopeKey: string;
  date: string;
  timezone: string;
  asOfSequence: number;
};

export function canLoadTodayPage(input: {
  hasCursor: boolean;
  loading: boolean;
  visible: TodaySnapshotIdentity | null;
  scopeKey: string;
  date: string;
  timezone: string;
  asOfSequence: number | undefined;
}): boolean {
  const {
    hasCursor,
    loading,
    visible,
    scopeKey,
    date,
    timezone,
    asOfSequence,
  } = input;
  return Boolean(
    hasCursor &&
      !loading &&
      asOfSequence !== undefined &&
      visible?.scopeKey === scopeKey &&
      visible.date === date &&
      visible.timezone === timezone &&
      visible.asOfSequence === asOfSequence,
  );
}

export function pageMatchesTodaySnapshot(
  page: TodayResponse,
  visible: TodaySnapshotIdentity | null,
  scopeKey: string,
): boolean {
  return Boolean(
    visible &&
      visible.scopeKey === scopeKey &&
      page.date === visible.date &&
      page.timezone === visible.timezone &&
      page.as_of_sequence === visible.asOfSequence,
  );
}
