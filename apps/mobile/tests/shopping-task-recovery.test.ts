import { describe, expect, it } from "vitest";

import {
  clearShoppingTaskRecord,
  loadShoppingTaskRecord,
  phaseAfterTaskFailure,
  phaseForTaskStatus,
  saveShoppingTaskRecord,
  SHOPPING_TASK_RECOVERY_KEY,
  type ShoppingTaskStorage,
} from "../src/features/profile/shoppingTaskRecovery";

class MemoryStorage implements ShoppingTaskStorage {
  values = new Map<string, string>();

  async getItemAsync(key: string) {
    return this.values.get(key) ?? null;
  }

  async setItemAsync(key: string, value: string) {
    this.values.set(key, value);
  }

  async deleteItemAsync(key: string) {
    this.values.delete(key);
  }
}

function record(phase: "creating_command" | "applying" = "creating_command") {
  return {
    schema_version: 1 as const,
    owner_id: "owner-a",
    command_id: "00000000-0000-0000-0000-000000000001",
    create_request: {
      command_id: "00000000-0000-0000-0000-000000000001",
      shopping_project_id: "00000000-0000-0000-0000-000000000002",
      expected_project_revision: 3,
    },
    phase,
    confirmation_id: phase === "applying" ? "00000000-0000-0000-0000-000000000003" : null,
  };
}

describe("Shopping source-task recovery state", () => {
  it("treats a create 409 as definitive and permits correction", () => {
    expect(phaseAfterTaskFailure("creating_command", { status: 409 })).toBe(
      "draft",
    );
  });

  it("keeps the same command and body after a create timeout", () => {
    expect(phaseAfterTaskFailure("creating_command", new TypeError("timeout"))).toBe(
      "creating_command",
    );
  });

  it("retries an ambiguous submission with the existing command identity", () => {
    expect(phaseAfterTaskFailure("submitting", new TypeError("timeout"))).toBe(
      "submitting",
    );
  });

  it("treats definitive validation rejection as terminal", () => {
    expect(phaseAfterTaskFailure("validating", { status: 409 })).toBe("terminal");
    expect(phaseForTaskStatus("rejected")).toBe("terminal");
  });

  it("marks a lost apply acknowledgement effect-unknown", () => {
    expect(phaseAfterTaskFailure("applying", new TypeError("timeout"))).toBe(
      "effect_unknown",
    );
    expect(phaseForTaskStatus("uncertain")).toBe("effect_unknown");
  });

  it("restores the original confirmation and execution identity after remount", async () => {
    const storage = new MemoryStorage();
    const original = record("applying");
    await saveShoppingTaskRecord(storage, original);

    const restored = await loadShoppingTaskRecord(storage, "owner-a");
    expect(restored).toEqual(original);
    expect(restored?.confirmation_id).toBe(original.confirmation_id);
    expect(JSON.stringify(restored)).not.toContain("preview");
  });

  it("clears recoverable state when the authenticated owner changes", async () => {
    const storage = new MemoryStorage();
    await saveShoppingTaskRecord(storage, record());

    expect(await loadShoppingTaskRecord(storage, "owner-b")).toBeNull();
    expect(storage.values.has(SHOPPING_TASK_RECOVERY_KEY)).toBe(false);
    await clearShoppingTaskRecord(storage);
  });
});
