/* Generated from contracts/openapi/openapi.json. Do not edit by hand. */

export interface components {
  schemas: {
    BooleanValue: {
      type: "boolean";
      value: boolean;
    };
    ConfirmationStatus: "unconfirmed" | "user_confirmed";
    ErrorResponse: {
      code: string;
      field_errors?: Array<components["schemas"]["FieldError"]> | null;
      message: string;
      request_id: string;
    };
    FieldError: {
      field: string;
      message: string;
    };
    FiniteProfileNumber: number;
    MetadataKey: string;
    MetadataScalar: string | number | number | boolean | null;
    NumberValue: {
      type: "number";
      value: components["schemas"]["FiniteProfileNumber"];
    };
    ProfileCategory: "background" | "constraints" | "preferences";
    ProfileCreateRequest: {
      ai_use_allowed?: boolean;
      cross_domain_use_allowed?: boolean;
      id: string;
      metadata?: components["schemas"]["ProfileMetadata"];
      notes?: string | null;
      profile: components["schemas"]["ProfilePayloadV1"];
      valid_from?: components["schemas"]["UTCInstant"] | null;
      valid_to?: components["schemas"]["UTCInstant"] | null;
    };
    ProfileHistoryEntry: {
      actor_kind: "user";
      reason: "create" | "update" | "archive";
      recorded_at: string;
      revision: number;
      snapshot: components["schemas"]["ProfileItemResponse"];
    };
    ProfileHistoryResponse: {
      items: Array<components["schemas"]["ProfileHistoryEntry"]>;
      next_after_revision: number | null;
    };
    ProfileItemResponse: {
      confirmation_status: components["schemas"]["ConfirmationStatus"];
      created_at: string;
      domain: "profile";
      id: string;
      metadata: components["schemas"]["ProfileMetadata"];
      notes: string | null;
      object_type: "profile_item";
      permissions: components["schemas"]["ProfilePermissions"];
      profile: components["schemas"]["ProfilePayloadV1"];
      recorded_at: string;
      revision: number;
      schema_version: 1;
      source: components["schemas"]["ProfileSource"];
      status: "active" | "archived";
      title: string;
      updated_at: string;
      valid_from: string | null;
      valid_to: string | null;
    };
    ProfileKind: "fact" | "constraint" | "preference";
    ProfileListResponse: {
      as_of: string;
      items: Array<components["schemas"]["ProfileItemResponse"]>;
      next_cursor: string | null;
    };
    ProfileMetadata: {
      [key: string]: components["schemas"]["MetadataScalar"];
    };
    ProfilePatchRequest: {
      ai_use_allowed?: boolean;
      cross_domain_use_allowed?: boolean;
      expected_revision: number;
      metadata?: components["schemas"]["ProfileMetadata"] | null;
      notes?: string | null;
      profile?: components["schemas"]["ProfilePayloadV1"];
      valid_from?: string | null;
      valid_to?: string | null;
    };
    ProfilePayloadV1: {
      category: components["schemas"]["ProfileCategory"];
      key: string;
      kind: components["schemas"]["ProfileKind"];
      label: string;
      value: components["schemas"]["ProfileValue"] | null;
    };
    ProfilePermissions: {
      ai_use_allowed: boolean;
      cross_domain_use_allowed: boolean;
    };
    ProfileSource: {
      id: string;
      kind: "manual" | "device" | "document" | "provider" | "ai" | "system";
      name: string;
    };
    ProfileUnit:
      | "kg"
      | "g"
      | "lb"
      | "mg"
      | "mcg"
      | "ml"
      | "l"
      | "cm"
      | "m"
      | "in"
      | "mmHg"
      | "bpm"
      | "%"
      | "day"
      | "week"
      | "year"
      | "dose";
    ProfileValue:
      | components["schemas"]["TextValue"]
      | components["schemas"]["BooleanValue"]
      | components["schemas"]["NumberValue"]
      | components["schemas"]["QuantityValue"]
      | components["schemas"]["TextListValue"];
    QuantityValue: {
      type: "quantity";
      unit: components["schemas"]["ProfileUnit"];
      value: components["schemas"]["FiniteProfileNumber"];
    };
    TextListValue: {
      type: "text_list";
      value: Array<string>;
    };
    TextValue: {
      type: "text";
      value: string;
    };
    UTCInstant: string;
  };
}

export interface operations {
  archiveProfileItem: {
    path: {
      item_id: string;
    };
    query: {
      expected_revision: number;
    };
    responses: {
      "200": components["schemas"]["ProfileItemResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "404": components["schemas"]["ErrorResponse"];
      "409": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  createProfileItem: {
    requestBody: components["schemas"]["ProfileCreateRequest"];
    responses: {
      "200": components["schemas"]["ProfileItemResponse"];
      "201": components["schemas"]["ProfileItemResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "409": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  getProfileItem: {
    path: {
      item_id: string;
    };
    responses: {
      "200": components["schemas"]["ProfileItemResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "404": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  healthcheck: {
    responses: {
      "200": {
        [key: string]: string;
      };
    };
  };
  listProfileHistory: {
    path: {
      item_id: string;
    };
    query?: {
      after_revision?: number;
      limit?: number;
    };
    responses: {
      "200": components["schemas"]["ProfileHistoryResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "404": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  listProfileItems: {
    query?: {
      as_of?: string | null;
      category?: components["schemas"]["ProfileCategory"] | null;
      limit?: number;
      cursor?: string | null;
    };
    responses: {
      "200": components["schemas"]["ProfileListResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  updateProfileItem: {
    path: {
      item_id: string;
    };
    requestBody: components["schemas"]["ProfilePatchRequest"];
    responses: {
      "200": components["schemas"]["ProfileItemResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "404": components["schemas"]["ErrorResponse"];
      "409": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
}

export type FetchResponse = {
  ok: boolean;
  status: number;
  json(): Promise<unknown>;
};
export type FetchLike = (
  input: string,
  init?: { method: string; headers?: Record<string, string>; body?: string },
) => Promise<FetchResponse>;

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body?: components["schemas"]["ErrorResponse"],
  ) {
    super(body?.message ?? `Request failed with status ${status}`);
    this.name = "ApiError";
  }
}

export class ProfileApiClient {
  private readonly baseUrl: string;
  private readonly fetcher: FetchLike;

  constructor(
    baseUrl: string,
    fetcher: FetchLike = globalThis.fetch as FetchLike,
  ) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.fetcher = fetcher;
  }

  async archiveProfileItem(
    path: operations["archiveProfileItem"]["path"],
    query: operations["archiveProfileItem"]["query"],
  ): Promise<components["schemas"]["ProfileItemResponse"]> {
    return this.request<components["schemas"]["ProfileItemResponse"]>(
      "DELETE",
      `/profile/${encodeURIComponent(path.item_id)}`,
      query,
      undefined,
    );
  }

  async createProfileItem(
    requestBody: operations["createProfileItem"]["requestBody"],
  ): Promise<components["schemas"]["ProfileItemResponse"]> {
    return this.request<components["schemas"]["ProfileItemResponse"]>(
      "POST",
      `/profile`,
      undefined,
      requestBody,
    );
  }

  async getProfileItem(
    path: operations["getProfileItem"]["path"],
  ): Promise<components["schemas"]["ProfileItemResponse"]> {
    return this.request<components["schemas"]["ProfileItemResponse"]>(
      "GET",
      `/profile/${encodeURIComponent(path.item_id)}`,
      undefined,
      undefined,
    );
  }

  async healthcheck(): Promise<{
    [key: string]: string;
  }> {
    return this.request<{
      [key: string]: string;
    }>("GET", `/healthz`, undefined, undefined);
  }

  async listProfileHistory(
    path: operations["listProfileHistory"]["path"],
    query?: operations["listProfileHistory"]["query"],
  ): Promise<components["schemas"]["ProfileHistoryResponse"]> {
    return this.request<components["schemas"]["ProfileHistoryResponse"]>(
      "GET",
      `/profile/${encodeURIComponent(path.item_id)}/history`,
      query,
      undefined,
    );
  }

  async listProfileItems(
    query?: operations["listProfileItems"]["query"],
  ): Promise<components["schemas"]["ProfileListResponse"]> {
    return this.request<components["schemas"]["ProfileListResponse"]>(
      "GET",
      `/profile`,
      query,
      undefined,
    );
  }

  async updateProfileItem(
    path: operations["updateProfileItem"]["path"],
    requestBody: operations["updateProfileItem"]["requestBody"],
  ): Promise<components["schemas"]["ProfileItemResponse"]> {
    return this.request<components["schemas"]["ProfileItemResponse"]>(
      "PATCH",
      `/profile/${encodeURIComponent(path.item_id)}`,
      undefined,
      requestBody,
    );
  }

  private async request<T>(
    method: string,
    path: string,
    query?: object,
    body?: unknown,
  ): Promise<T> {
    const params = new URLSearchParams();
    if (query) {
      for (const [key, value] of Object.entries(query)) {
        if (value !== undefined && value !== null)
          params.set(key, String(value));
      }
    }
    const serialized = params.toString();
    const suffix = serialized ? `?${serialized}` : "";
    const response = await this.fetcher(`${this.baseUrl}${path}${suffix}`, {
      method,
      ...(body === undefined
        ? {}
        : {
            headers: { "content-type": "application/json" },
            body: JSON.stringify(body),
          }),
    });
    const payload = await response.json().catch(() => undefined);
    if (!response.ok)
      throw new ApiError(
        response.status,
        payload as components["schemas"]["ErrorResponse"] | undefined,
      );
    return payload as T;
  }
}
