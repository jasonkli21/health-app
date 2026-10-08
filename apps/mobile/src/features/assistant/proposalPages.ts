export type ProposalPageFilter =
  | "pending"
  | "applied"
  | "rejected"
  | "expired"
  | "superseded";

export interface ProposalPageLease {
  append: boolean;
  cursor: string | null;
  dataGeneration: number;
  filter: ProposalPageFilter;
  focusGeneration: number;
  requestGeneration: number;
}

export class ProposalPageCoordinator {
  private currentFilter: ProposalPageFilter = "pending";
  private currentCursor: string | null = null;
  private focusGeneration = 0;
  private requestGeneration = 0;

  get cursor(): string | null {
    return this.currentCursor;
  }

  focus(): void {
    this.focusGeneration += 1;
    this.requestGeneration += 1;
    this.currentCursor = null;
  }

  blur(): void {
    this.focusGeneration += 1;
    this.requestGeneration += 1;
  }

  setFilter(filter: ProposalPageFilter): void {
    if (this.currentFilter === filter) return;
    this.currentFilter = filter;
    this.requestGeneration += 1;
    this.currentCursor = null;
  }

  invalidate(): void {
    this.requestGeneration += 1;
  }

  begin(append: boolean, dataGeneration: number): ProposalPageLease {
    if (!append) {
      this.requestGeneration += 1;
      this.currentCursor = null;
    }
    return {
      append,
      cursor: append ? this.currentCursor : null,
      dataGeneration,
      filter: this.currentFilter,
      focusGeneration: this.focusGeneration,
      requestGeneration: this.requestGeneration,
    };
  }

  accepts(lease: ProposalPageLease, dataGeneration: number): boolean {
    return (
      lease.focusGeneration === this.focusGeneration &&
      lease.requestGeneration === this.requestGeneration &&
      lease.dataGeneration === dataGeneration &&
      lease.filter === this.currentFilter
    );
  }

  complete(
    lease: ProposalPageLease,
    nextCursor: string | null,
    dataGeneration: number,
  ): boolean {
    if (!this.accepts(lease, dataGeneration)) return false;
    this.currentCursor = nextCursor;
    return true;
  }
}

export async function runProposalPageLoad<
  TPage extends { next_cursor: string | null },
>(options: {
  coordinator: ProposalPageCoordinator;
  append: boolean;
  dataGeneration: number;
  getDataGeneration: () => number;
  load: (
    filter: ProposalPageFilter,
    cursor: string | undefined,
  ) => Promise<TPage>;
  onPage: (page: TPage, append: boolean) => void;
  onLoading: (loading: boolean) => void;
  onErrorMessage: (message: string | null) => void;
  onCursor: (cursor: string | null) => void;
  requestMessage: (error: unknown) => string;
}): Promise<void> {
  const lease = options.coordinator.begin(
    options.append,
    options.dataGeneration,
  );
  if (!lease.append) options.onCursor(null);
  options.onErrorMessage(null);
  options.onLoading(true);
  try {
    const page = await options.load(lease.filter, lease.cursor ?? undefined);
    if (
      options.coordinator.complete(
        lease,
        page.next_cursor,
        options.getDataGeneration(),
      )
    ) {
      options.onCursor(page.next_cursor);
      options.onPage(page, lease.append);
    }
  } catch (error) {
    if (options.coordinator.accepts(lease, options.getDataGeneration())) {
      options.onErrorMessage(options.requestMessage(error));
    }
  } finally {
    if (options.coordinator.accepts(lease, options.getDataGeneration())) {
      options.onLoading(false);
    }
  }
}
