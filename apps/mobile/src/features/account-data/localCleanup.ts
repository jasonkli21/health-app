export interface OwnerCleanupStore {
  clearOwner(ownerId: string): Promise<void>;
}

export async function clearOwnerDeletionState(
  ownerId: string | null,
  consentStore: OwnerCleanupStore,
  checkpointStore: OwnerCleanupStore,
  removeRequestKey: () => Promise<void>,
): Promise<void> {
  if (ownerId) {
    await consentStore.clearOwner(ownerId);
    await checkpointStore.clearOwner(ownerId);
  }
  await removeRequestKey();
}
