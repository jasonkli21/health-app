import { draftFromDailyItem, type DailyDraft, type DailyItem } from "./model";

export type DailyEditState = {
  item: DailyItem | null;
  draft: DailyDraft | null;
  baseline: DailyDraft | null;
  dirty: boolean;
  formGeneration: number;
};

export const EMPTY_DAILY_EDIT_STATE: DailyEditState = {
  item: null,
  draft: null,
  baseline: null,
  dirty: false,
  formGeneration: 0,
};

export function recordDailyDraft(
  state: DailyEditState,
  draft: DailyDraft,
): DailyEditState {
  if (!state.baseline) return state;
  return {
    ...state,
    draft,
    dirty: JSON.stringify(draft) !== JSON.stringify(state.baseline),
  };
}

export function acceptDailyRefresh(
  state: DailyEditState,
  incoming: DailyItem,
  explicitlyReloaded = false,
): DailyEditState {
  if (state.dirty && !explicitlyReloaded && state.item?.id === incoming.id) {
    return state;
  }
  const draft = draftFromDailyItem(incoming);
  return {
    item: incoming,
    draft,
    baseline: draft,
    dirty: false,
    formGeneration: state.formGeneration + 1,
  };
}
