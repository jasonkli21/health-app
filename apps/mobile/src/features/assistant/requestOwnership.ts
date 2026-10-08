export type AssistantRequestKind = "message" | "preview" | "search";

export interface AssistantRequestLease {
  id: number;
  kind: AssistantRequestKind;
  generation: number;
  focusGeneration: number;
  key: string;
}

export class AssistantRequestOwnership {
  private nextId = 0;
  private focusGeneration = 0;
  private readonly generations: Record<AssistantRequestKind, number> = {
    message: 0,
    preview: 0,
    search: 0,
  };
  private readonly keys: Partial<Record<AssistantRequestKind, string>> = {};
  private activeBusy: AssistantRequestLease | null = null;

  get busy(): boolean {
    return this.activeBusy !== null;
  }

  begin(kind: AssistantRequestKind, key: string): AssistantRequestLease {
    if (this.activeBusy) {
      this.generations[this.activeBusy.kind] += 1;
    }
    const generation = this.generations[kind] + 1;
    this.generations[kind] = generation;
    this.keys[kind] = key;
    const lease = {
      id: ++this.nextId,
      kind,
      generation,
      focusGeneration: this.focusGeneration,
      key,
    };
    this.activeBusy = lease;
    return lease;
  }

  changeKey(kind: AssistantRequestKind, key: string): boolean {
    if (this.keys[kind] === key) return false;
    this.keys[kind] = key;
    this.generations[kind] += 1;
    return this.releaseBusy(kind);
  }

  invalidate(kind: AssistantRequestKind): boolean {
    this.generations[kind] += 1;
    return this.releaseBusy(kind);
  }

  focusChanged(): boolean {
    const hadBusyOperation = this.activeBusy !== null;
    this.focusGeneration += 1;
    for (const kind of Object.keys(
      this.generations,
    ) as AssistantRequestKind[]) {
      this.generations[kind] += 1;
    }
    this.activeBusy = null;
    return hadBusyOperation;
  }

  accepts(lease: AssistantRequestLease): boolean {
    return (
      lease.focusGeneration === this.focusGeneration &&
      lease.generation === this.generations[lease.kind] &&
      lease.key === this.keys[lease.kind]
    );
  }

  finish(lease: AssistantRequestLease): boolean {
    if (this.activeBusy?.id !== lease.id) return false;
    this.activeBusy = null;
    return true;
  }

  private releaseBusy(kind: AssistantRequestKind): boolean {
    if (this.activeBusy?.kind !== kind) return false;
    this.activeBusy = null;
    return true;
  }
}

export async function runOwnedAssistantRequest<T>(options: {
  ownership: AssistantRequestOwnership;
  kind: AssistantRequestKind;
  key: string;
  request: () => Promise<T>;
  onSuccess: (result: T) => void;
  onError: (error: unknown) => void;
  onBusyChange: (busy: boolean) => void;
}): Promise<void> {
  const lease = options.ownership.begin(options.kind, options.key);
  options.onBusyChange(true);
  try {
    const result = await options.request();
    if (options.ownership.accepts(lease)) options.onSuccess(result);
  } catch (error) {
    if (options.ownership.accepts(lease)) options.onError(error);
  } finally {
    if (options.ownership.finish(lease)) {
      options.onBusyChange(options.ownership.busy);
    }
  }
}
