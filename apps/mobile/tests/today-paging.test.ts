import { describe, expect, it } from "vitest";

import {
  RequestScope,
  requestNextPage,
} from "../src/features/profile/requestScope";
import {
  canLoadTodayPage,
  pageMatchesTodaySnapshot,
  type TodaySnapshotIdentity,
} from "../src/features/daily/todayPaging";
import type { components } from "@personal-health/api-client";

const page = (
  date: string,
  timezone: string,
  sequence: number,
): components["schemas"]["TodayResponse"] =>
  ({
    date,
    timezone,
    as_of_sequence: sequence,
  }) as components["schemas"]["TodayResponse"];

describe("Today timeline page scope", () => {
  it("blocks an old cursor while a same-day refresh is pending or has failed", () => {
    const previous: TodaySnapshotIdentity = {
      scopeKey: "today:2026-10-04:UTC:0",
      date: "2026-10-04",
      timezone: "UTC",
      asOfSequence: 7,
    };
    expect(
      canLoadTodayPage({
        hasCursor: true,
        loading: true,
        visible: previous,
        scopeKey: "today:2026-10-04:UTC:1",
        date: previous.date,
        timezone: previous.timezone,
        asOfSequence: previous.asOfSequence,
      }),
    ).toBe(false);
    expect(
      canLoadTodayPage({
        hasCursor: true,
        loading: false,
        visible: previous,
        scopeKey: "today:2026-10-04:UTC:1",
        date: previous.date,
        timezone: previous.timezone,
        asOfSequence: previous.asOfSequence,
      }),
    ).toBe(false);
  });

  it("rejects a page whose sequence, date, timezone, or scope differs from the visible result", () => {
    const visible: TodaySnapshotIdentity = {
      scopeKey: "today:2026-10-04:UTC:2",
      date: "2026-10-04",
      timezone: "UTC",
      asOfSequence: 9,
    };
    expect(
      pageMatchesTodaySnapshot(
        page(visible.date, visible.timezone, 9),
        visible,
        visible.scopeKey,
      ),
    ).toBe(true);
    expect(
      pageMatchesTodaySnapshot(
        page(visible.date, visible.timezone, 8),
        visible,
        visible.scopeKey,
      ),
    ).toBe(false);
    expect(
      pageMatchesTodaySnapshot(
        page("2026-10-03", visible.timezone, 9),
        visible,
        visible.scopeKey,
      ),
    ).toBe(false);
    expect(
      pageMatchesTodaySnapshot(
        page(visible.date, "America/Los_Angeles", 9),
        visible,
        visible.scopeKey,
      ),
    ).toBe(false);
    expect(
      pageMatchesTodaySnapshot(
        page(visible.date, visible.timezone, 9),
        visible,
        "new-scope",
      ),
    ).toBe(false);
  });

  it("does not apply an out-of-order page after the refresh starts a new request scope", async () => {
    const requests = new RequestScope();
    const old = requests.start("today:2026-10-04:UTC:0");
    const visible: TodaySnapshotIdentity = {
      scopeKey: old.scope,
      date: "2026-10-04",
      timezone: "UTC",
      asOfSequence: 9,
    };
    const refreshed = requests.start("today:2026-10-04:UTC:1");
    let applied = false;
    await requestNextPage(
      requests,
      old,
      "old-cursor",
      async () => page(visible.date, visible.timezone, visible.asOfSequence),
      {
        onStart: () => undefined,
        onSuccess: () => {
          applied = true;
        },
        onError: () => undefined,
        onFinish: () => undefined,
      },
    );
    expect(requests.isCurrent(refreshed)).toBe(true);
    expect(applied).toBe(false);
  });
});
