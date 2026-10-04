export type RequestToken = { generation: number; scope: string };

export class RequestScope {
  private generation = 0;
  private scope: string | null = null;
  private active = false;
  private readonly pagesInFlight = new Set<string>();

  start(scope: string): RequestToken {
    this.generation += 1;
    this.scope = scope;
    this.active = true;
    this.pagesInFlight.clear();
    return { generation: this.generation, scope };
  }

  invalidate(token: RequestToken): void {
    if (!this.isCurrent(token)) return;
    this.active = false;
    this.scope = null;
    this.generation += 1;
    this.pagesInFlight.clear();
  }

  tokenFor(scope: string): RequestToken | null {
    if (!this.active || this.scope !== scope) return null;
    return { generation: this.generation, scope };
  }

  isCurrent(token: RequestToken): boolean {
    return (
      this.active &&
      this.generation === token.generation &&
      this.scope === token.scope
    );
  }

  beginPage(token: RequestToken, cursor: string): boolean {
    if (!this.isCurrent(token)) return false;
    const key = `${token.generation}:${cursor}`;
    if (this.pagesInFlight.has(key)) return false;
    this.pagesInFlight.add(key);
    return true;
  }

  finishPage(token: RequestToken, cursor: string): void {
    this.pagesInFlight.delete(`${token.generation}:${cursor}`);
  }
}

type PageHandlers<T> = {
  onStart: () => void;
  onSuccess: (page: T) => void;
  onError: (error: unknown) => void;
  onFinish: () => void;
};

export async function requestNextPage<T>(
  scope: RequestScope,
  token: RequestToken,
  cursor: string,
  request: () => Promise<T>,
  handlers: PageHandlers<T>,
): Promise<void> {
  if (!scope.beginPage(token, cursor)) return;
  handlers.onStart();
  try {
    const page = await request();
    if (scope.isCurrent(token)) handlers.onSuccess(page);
  } catch (error) {
    if (scope.isCurrent(token)) handlers.onError(error);
  } finally {
    scope.finishPage(token, cursor);
    if (scope.isCurrent(token)) handlers.onFinish();
  }
}
