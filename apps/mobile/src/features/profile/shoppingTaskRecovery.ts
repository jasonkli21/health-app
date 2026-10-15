export type ShoppingTaskPhase =
  | "draft"
  | "creating_command"
  | "command_created"
  | "submitting"
  | "validating"
  | "proposed"
  | "validated"
  | "confirming"
  | "confirmed"
  | "applying"
  | "effect_unknown"
  | "terminal";

export type ShoppingTaskRecord = {
  schema_version: 1;
  owner_id: string;
  command_id: string;
  create_request: Record<string, unknown>;
  phase: ShoppingTaskPhase;
  confirmation_id: string | null;
};

export type ShoppingTaskStorage = {
  getItemAsync(key: string): Promise<string | null>;
  setItemAsync(key: string, value: string): Promise<void>;
  deleteItemAsync(key: string): Promise<void>;
};

export const SHOPPING_TASK_RECOVERY_KEY = "health.shopping-task-recovery.v1";
let storageQueue: Promise<void> = Promise.resolve();

function serializeStorage<T>(work: () => Promise<T>): Promise<T> {
  const next = storageQueue.then(work, work);
  storageQueue = next.then(
    () => undefined,
    () => undefined,
  );
  return next;
}

const phases = new Set<ShoppingTaskPhase>([
  "draft",
  "creating_command",
  "command_created",
  "submitting",
  "validating",
  "proposed",
  "validated",
  "confirming",
  "confirmed",
  "applying",
  "effect_unknown",
  "terminal",
]);

export async function loadShoppingTaskRecord(
  storage: ShoppingTaskStorage,
  ownerId: string,
): Promise<ShoppingTaskRecord | null> {
  const raw = await serializeStorage(() =>
    storage.getItemAsync(SHOPPING_TASK_RECOVERY_KEY),
  );
  if (!raw) return null;
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    await serializeStorage(() =>
      storage.deleteItemAsync(SHOPPING_TASK_RECOVERY_KEY),
    );
    return null;
  }
  if (
    !value ||
    typeof value !== "object" ||
    (value as ShoppingTaskRecord).schema_version !== 1 ||
    (value as ShoppingTaskRecord).owner_id !== ownerId ||
    typeof (value as ShoppingTaskRecord).command_id !== "string" ||
    !phases.has((value as ShoppingTaskRecord).phase) ||
    !(value as ShoppingTaskRecord).create_request ||
    typeof (value as ShoppingTaskRecord).create_request !== "object"
  ) {
    await serializeStorage(() =>
      storage.deleteItemAsync(SHOPPING_TASK_RECOVERY_KEY),
    );
    return null;
  }
  return value as ShoppingTaskRecord;
}

export async function saveShoppingTaskRecord(
  storage: ShoppingTaskStorage,
  record: ShoppingTaskRecord,
): Promise<void> {
  await serializeStorage(() =>
    storage.setItemAsync(SHOPPING_TASK_RECOVERY_KEY, JSON.stringify(record)),
  );
}

export async function clearShoppingTaskRecord(
  storage: ShoppingTaskStorage,
): Promise<void> {
  await serializeStorage(() =>
    storage.deleteItemAsync(SHOPPING_TASK_RECOVERY_KEY),
  );
}

export function isDefinitiveTaskFailure(error: unknown): boolean {
  const status = (error as { status?: unknown } | null)?.status;
  return typeof status === "number" && status >= 400 && status < 500;
}

export function phaseAfterTaskFailure(
  phase: ShoppingTaskPhase,
  error: unknown,
): ShoppingTaskPhase {
  if (phase === "creating_command") {
    return isDefinitiveTaskFailure(error) ? "draft" : "creating_command";
  }
  if (phase === "submitting") {
    return isDefinitiveTaskFailure(error) ? "terminal" : "submitting";
  }
  if (phase === "applying") {
    return isDefinitiveTaskFailure(error) ? "terminal" : "effect_unknown";
  }
  if (phase === "confirming" || phase === "validating") {
    return isDefinitiveTaskFailure(error) ? "terminal" : phase;
  }
  return phase;
}

export function phaseForTaskStatus(state: string): ShoppingTaskPhase {
  if (state === "proposed") return "proposed";
  if (state === "validated") return "validated";
  if (state === "confirmed") return "confirmed";
  if (["executing", "reconciling", "uncertain"].includes(state)) {
    return "effect_unknown";
  }
  return "terminal";
}
