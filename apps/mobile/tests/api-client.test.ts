import { describe, expect, it } from "vitest";

import { ApiError, ProfileApiClient } from "@personal-health/api-client";
import type { FetchLike, components } from "@personal-health/api-client";

function response(payload: unknown, ok = true, status = 200) {
  return { ok, status, json: async () => payload };
}

describe("generated Profile API client", () => {
  it("serializes typed list filters and safely encodes path identifiers", async () => {
    const requests: { url: string; init?: Parameters<FetchLike>[1] }[] = [];
    const fetcher: FetchLike = async (url, init) => {
      requests.push({ url, init });
      return response({
        items: [],
        as_of: "2026-10-03T12:00:00Z",
        next_cursor: null,
      });
    };
    const client = new ProfileApiClient("https://localhost:8000/", fetcher);

    await client.listProfileItems({
      as_of: "2026-10-03T12:00:00Z",
      category: "background",
    });
    await client.getProfileItem({ item_id: "id/with space" });

    expect(requests[0].url).toBe(
      "https://localhost:8000/profile?as_of=2026-10-03T12%3A00%3A00Z&category=background",
    );
    expect(requests[1].url).toBe(
      "https://localhost:8000/profile/id%2Fwith%20space",
    );
  });

  it("serializes the typed create request and raises a structured API error", async () => {
    const request: components["schemas"]["ProfileCreateRequest"] = {
      id: "00000000-0000-0000-0000-000000000001",
      profile: {
        kind: "fact",
        category: "background",
        key: "medication_note",
        label: "Medication note",
        value: null,
      },
    };
    let capturedBody: string | undefined;
    const successful: FetchLike = async (_url, init) => {
      capturedBody = init?.body;
      return response({ id: request.id, revision: 1 });
    };
    await new ProfileApiClient(
      "https://localhost:8000",
      successful,
    ).createProfileItem(request);
    expect(JSON.parse(capturedBody ?? "{}")).toEqual(request);

    const failing: FetchLike = async () =>
      response(
        {
          code: "conflict",
          message: "Profile item has changed; reload before saving",
          request_id: "request-1",
        },
        false,
        409,
      );
    await expect(
      new ProfileApiClient("https://localhost:8000", failing).getProfileItem({
        item_id: request.id,
      }),
    ).rejects.toMatchObject({
      name: "ApiError",
      status: 409,
      body: {
        code: "conflict",
        message: "Profile item has changed; reload before saving",
        request_id: "request-1",
      },
    } satisfies Partial<ApiError>);
  });

  it("has compile-time access to Profile v1 values including unknown, false, and zero", () => {
    const knownFalse: components["schemas"]["ProfilePayloadV1"] = {
      kind: "fact",
      category: "background",
      key: "has_allergy",
      label: "Has an allergy",
      value: { type: "boolean", value: false },
    };
    const unknown: components["schemas"]["ProfilePayloadV1"] = {
      ...knownFalse,
      value: null,
    };
    const zero: components["schemas"]["ProfilePayloadV1"] = {
      ...knownFalse,
      value: { type: "number", value: 0 },
    };
    expect(knownFalse.value).toEqual({ type: "boolean", value: false });
    expect(unknown.value).toBeNull();
    expect(zero.value).toEqual({ type: "number", value: 0 });

    const partialUpdate: components["schemas"]["ProfilePatchRequest"] = {
      expected_revision: 1,
      ai_use_allowed: false,
    };
    expect(partialUpdate.ai_use_allowed).toBe(false);
    const rejectedNull = {
      expected_revision: 1,
      // @ts-expect-error The API rejects explicit null for profile content.
      profile: null,
    } satisfies components["schemas"]["ProfilePatchRequest"];
    expect(rejectedNull.profile).toBeNull();
  });
});
