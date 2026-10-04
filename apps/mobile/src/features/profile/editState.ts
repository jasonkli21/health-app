import { draftFromProfile, type ProfileDraft, type ProfileItem } from "./model";

export type ProfileEditState = {
  item: ProfileItem | null;
  draft: ProfileDraft | null;
  baseline: ProfileDraft | null;
  dirty: boolean;
  formGeneration: number;
};

export const EMPTY_PROFILE_EDIT_STATE: ProfileEditState = {
  item: null,
  draft: null,
  baseline: null,
  dirty: false,
  formGeneration: 0,
};

export function recordProfileDraft(
  state: ProfileEditState,
  draft: ProfileDraft,
): ProfileEditState {
  if (!state.baseline) return state;
  return {
    ...state,
    draft,
    dirty: JSON.stringify(draft) !== JSON.stringify(state.baseline),
  };
}

export function acceptProfileRefresh(
  state: ProfileEditState,
  incoming: ProfileItem,
  explicitlyReloaded = false,
): ProfileEditState {
  if (state.dirty && !explicitlyReloaded && state.item?.id === incoming.id) {
    return state;
  }
  const draft = draftFromProfile(incoming);
  return {
    item: incoming,
    draft,
    baseline: draft,
    dirty: false,
    formGeneration: state.formGeneration + 1,
  };
}
