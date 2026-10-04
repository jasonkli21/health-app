import { ApiError, ProfileApiClient } from "@personal-health/api-client";
import type { FetchLike } from "@personal-health/api-client";
import { describe, expect, it } from "vitest";

import {
  EMPTY_PROFILE_DRAFT,
  buildProfileFields,
} from "../src/features/profile/model";
import { ProfileCreateRecovery } from "../src/features/profile/createRecovery";

function fields(label: string) {
  const result = buildProfileFields({
    ...EMPTY_PROFILE_DRAFT,
    key: "preferred_name",
    label,
  });
  if (!result.ok) throw new Error(result.error);
  return result.fields;
}

describe("Profile create recovery", () => {
  it("retries the original id and body after a lost response before allowing edits", async () => {
    const recovery = new ProfileCreateRecovery();
    const id = "00000000-0000-0000-0000-000000000001";
    const original = recovery.prepare(id, fields("Preferred name"));
    const requests: unknown[] = [];
    let firstRequest = true;
    const fetcher: FetchLike = async (_url, init) => {
      requests.push(JSON.parse(init?.body ?? "{}"));
      if (firstRequest) {
        firstRequest = false;
        throw new TypeError("response lost after commit");
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ id, revision: 1 }),
      };
    };
    const client = new ProfileApiClient("https://localhost:8000", fetcher);

    await expect(
      client.createProfileItem({ id: original.id, ...original.fields }),
    ).rejects.toThrow("response lost");
    expect(recovery.markFailure(original, new TypeError("response lost"))).toBe(
      true,
    );
    expect(recovery.isUncertain).toBe(true);

    expect(() => recovery.prepare(id, fields("Changed draft"))).toThrow(
      "Retry the original save",
    );
    expect(requests).toHaveLength(1);

    const retry = recovery.retryOriginal();
    expect(retry).toEqual(original);
    await client.createProfileItem({ id: retry!.id, ...retry!.fields });
    expect(requests[1]).toEqual(requests[0]);
    recovery.resolve();
    expect(recovery.isUncertain).toBe(false);
  });

  it("lets the user correct a known validation failure without changing identity", () => {
    const recovery = new ProfileCreateRecovery();
    const id = "00000000-0000-0000-0000-000000000001";
    const rejected = recovery.prepare(id, fields("Preferred name"));

    expect(recovery.markFailure(rejected, new ApiError(422))).toBe(false);
    expect(recovery.isUncertain).toBe(false);
    expect(recovery.prepare(id, fields("Updated label"))).toEqual({
      id,
      fields: fields("Updated label"),
    });
  });

  it("keeps server failures uncertain because the create may have committed", () => {
    const recovery = new ProfileCreateRecovery();
    const attempt = recovery.prepare(
      "00000000-0000-0000-0000-000000000001",
      fields("Preferred name"),
    );

    expect(recovery.markFailure(attempt, new ApiError(503))).toBe(true);
    expect(recovery.retryOriginal()).toEqual(attempt);
  });
});
