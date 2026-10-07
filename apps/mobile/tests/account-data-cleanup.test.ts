import { describe, expect, it, vi } from "vitest";

import { clearOwnerDeletionState } from "../src/features/account-data/localCleanup";

describe("account deletion local cleanup", () => {
  it.each(["consent", "checkpoints", "request key"] as const)(
    "keeps cleanup retryable when %s removal fails",
    async (failedStep) => {
      let failed = true;
      const consentStore = {
        clearOwner: vi.fn(async () => {
          if (failed && failedStep === "consent")
            throw new Error("secure store error");
        }),
      };
      const checkpointStore = {
        clearOwner: vi.fn(async () => {
          if (failed && failedStep === "checkpoints")
            throw new Error("secure store error");
        }),
      };
      const removeRequestKey = vi.fn(async () => {
        if (failed && failedStep === "request key")
          throw new Error("secure store error");
      });
      const clear = () =>
        clearOwnerDeletionState(
          "owner-a",
          consentStore,
          checkpointStore,
          removeRequestKey,
        );

      await expect(clear()).rejects.toThrow("secure store error");
      if (failedStep === "consent") {
        expect(checkpointStore.clearOwner).not.toHaveBeenCalled();
        expect(removeRequestKey).not.toHaveBeenCalled();
      } else if (failedStep === "checkpoints") {
        expect(consentStore.clearOwner).toHaveBeenCalledTimes(1);
        expect(removeRequestKey).not.toHaveBeenCalled();
      } else {
        expect(consentStore.clearOwner).toHaveBeenCalledTimes(1);
        expect(checkpointStore.clearOwner).toHaveBeenCalledTimes(1);
      }

      failed = false;
      await clear();
      expect(consentStore.clearOwner).toHaveBeenCalledTimes(2);
      expect(checkpointStore.clearOwner).toHaveBeenCalledTimes(
        failedStep === "consent" ? 1 : 2,
      );
      expect(removeRequestKey).toHaveBeenCalledTimes(
        failedStep === "request key" ? 2 : 1,
      );
    },
  );

  it("removes only the owner request key in development mode", async () => {
    const consentStore = { clearOwner: vi.fn() };
    const checkpointStore = { clearOwner: vi.fn() };
    const removeRequestKey = vi.fn(async () => undefined);

    await clearOwnerDeletionState(
      null,
      consentStore,
      checkpointStore,
      removeRequestKey,
    );

    expect(consentStore.clearOwner).not.toHaveBeenCalled();
    expect(checkpointStore.clearOwner).not.toHaveBeenCalled();
    expect(removeRequestKey).toHaveBeenCalledOnce();
  });
});
