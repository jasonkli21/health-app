/* Generated from contracts/openapi/openapi.json. Do not edit by hand. */

export interface components {
  schemas: {
    BooleanValue: {
      type: "boolean";
      value: boolean;
    };
    ConfirmationStatus: "unconfirmed" | "user_confirmed";
    CoverageV1: {
      known_count: number;
      total_count: number;
    };
    DailyDomain:
      | "nutrition"
      | "exercise"
      | "sleep"
      | "symptoms"
      | "measurements";
    DailyEntryCreateRequest: {
      events?: Array<components["schemas"]["DailyEventCreateRequest"]>;
      links?: Array<components["schemas"]["DailyLinkRequest"]>;
      observations?: Array<
        components["schemas"]["DailyObservationCreateRequest"]
      >;
    };
    DailyEntryCreateResponse: {
      created: boolean;
      events: Array<components["schemas"]["DailyEventResponse"]>;
      observations: Array<components["schemas"]["DailyObservationResponse"]>;
    };
    DailyEventCreateRequest: {
      event: components["schemas"]["EventSchemaV1"];
      id: string;
    };
    DailyEventListResponse: {
      items: Array<components["schemas"]["DailyEventResponse"]>;
      next_cursor: string | null;
    };
    DailyEventResponse: {
      confirmation_status: components["schemas"]["ConfirmationStatus"];
      created_at: string;
      domain: components["schemas"]["DailyDomain"];
      event: components["schemas"]["EventSchemaV1"];
      id: string;
      linked_observation_ids: Array<string>;
      metadata: components["schemas"]["ProfileMetadata"];
      notes: string | null;
      object_type: "event";
      permissions: components["schemas"]["ProfilePermissions"];
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
    DailyEventUpdateRequest: {
      event: components["schemas"]["EventSchemaV1"];
      expected_revision: number;
    };
    DailyHistoryEntry: {
      actor_kind: "user";
      reason: "create" | "update" | "archive";
      recorded_at: string;
      revision: number;
      snapshot:
        | components["schemas"]["DailyEventResponse"]
        | components["schemas"]["DailyObservationResponse"];
    };
    DailyHistoryResponse: {
      items: Array<components["schemas"]["DailyHistoryEntry"]>;
      next_after_revision: number | null;
    };
    DailyLinkRequest: {
      event_id: string;
      observation_id: string;
      role?: "symptom_severity";
    };
    DailyObservationCreateRequest: {
      id: string;
      observation: components["schemas"]["ObservationSchemaV1"];
    };
    DailyObservationListResponse: {
      items: Array<components["schemas"]["DailyObservationResponse"]>;
      next_cursor: string | null;
    };
    DailyObservationResponse: {
      confirmation_status: components["schemas"]["ConfirmationStatus"];
      created_at: string;
      domain: components["schemas"]["DailyDomain"];
      id: string;
      metadata: components["schemas"]["ProfileMetadata"];
      notes: string | null;
      object_type: "observation";
      observation: components["schemas"]["ObservationSchemaV1"];
      permissions: components["schemas"]["ProfilePermissions"];
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
    DailyObservationUpdateRequest: {
      expected_revision: number;
      observation: components["schemas"]["ObservationSchemaV1"];
    };
    DailyTimePoint:
      | components["schemas"]["InstantTimePoint"]
      | components["schemas"]["DateOnlyTimePoint"];
    DateOnlyTimePoint: {
      local_date: string;
      precision: "date_only";
      timezone: string;
    };
    DistanceQuantity: {
      unit: "m" | "km" | "mi";
      value: components["schemas"]["FiniteProfileNumber"];
    };
    DurationQuantity: {
      unit: "min" | "h";
      value: components["schemas"]["FiniteProfileNumber"];
    };
    EnergyQuantity: {
      unit: "kcal" | "kJ";
      value: components["schemas"]["FiniteProfileNumber"];
    };
    ErrorResponse: {
      code: string;
      field_errors?: Array<components["schemas"]["FieldError"]> | null;
      message: string;
      request_id: string;
    };
    EventPayloadV1:
      | components["schemas"]["MealEventV1"]
      | components["schemas"]["WorkoutEventV1"]
      | components["schemas"]["SleepEventV1"]
      | components["schemas"]["SymptomEventV1"];
    EventSchemaV1: {
      domain: components["schemas"]["DailyDomain"];
      ended_at?: components["schemas"]["UTCInstant"] | null;
      notes?: string | null;
      payload: components["schemas"]["EventPayloadV1"];
      time: components["schemas"]["DailyTimePoint"];
    };
    FieldError: {
      field: string;
      message: string;
    };
    FiniteProfileNumber: number;
    InstantTimePoint: {
      occurred_at: components["schemas"]["UTCInstant"];
      precision: "instant";
      timezone: string;
    };
    MealEventV1: {
      energy?: components["schemas"]["EnergyQuantity"] | null;
      foods?: Array<string>;
      kind: "meal";
      label: string;
    };
    MeasurementUnit:
      | "kcal"
      | "kJ"
      | "min"
      | "h"
      | "m"
      | "km"
      | "mi"
      | "kg"
      | "lb"
      | "C"
      | "F"
      | "mmHg"
      | "bpm"
      | "score"
      | "episodes";
    MeasurementValueV1: {
      metric:
        | "weight"
        | "temperature"
        | "systolic_pressure"
        | "diastolic_pressure"
        | "pulse";
      unit: components["schemas"]["MeasurementUnit"];
      value: components["schemas"]["FiniteProfileNumber"];
    };
    MetadataKey: string;
    MetadataScalar: string | number | number | boolean | null;
    MetricKey:
      | "energy"
      | "duration"
      | "distance"
      | "weight"
      | "temperature"
      | "systolic_pressure"
      | "diastolic_pressure"
      | "pulse"
      | "symptom_severity"
      | "symptom_episode_count";
    MetricSummaryV1: {
      coverage: components["schemas"]["CoverageV1"];
      domain: components["schemas"]["DailyDomain"];
      known_value: number | null;
      logged_count: number;
      method_version: string;
      metric: components["schemas"]["MetricKey"];
      partial: boolean;
      unit: string;
    };
    NumberValue: {
      type: "number";
      value: components["schemas"]["FiniteProfileNumber"];
    };
    ObservationPayloadV1: {
      value: components["schemas"]["ObservationValueV1"];
    };
    ObservationSchemaV1: {
      domain: "measurements" | "symptoms";
      interval_end?: components["schemas"]["UTCInstant"] | null;
      notes?: string | null;
      payload: components["schemas"]["ObservationPayloadV1"];
      time: components["schemas"]["DailyTimePoint"];
    };
    ObservationValueV1:
      | components["schemas"]["MeasurementValueV1"]
      | components["schemas"]["SymptomSeverityV1"];
    ProfileCategory: "background" | "constraints" | "preferences";
    ProfileContextReference: {
      id: string;
      title: string;
    };
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
    SleepEventV1: {
      kind: "sleep";
      label?: string;
      quality?: number | null;
    };
    SymptomEventV1: {
      kind: "symptom";
      label: string;
    };
    SymptomSeverityV1: {
      metric: "symptom_severity";
      unit?: "score";
      value: number;
    };
    TextListValue: {
      type: "text_list";
      value: Array<string>;
    };
    TextValue: {
      type: "text";
      value: string;
    };
    TodayResponse: {
      as_of_sequence: number;
      date: string;
      includes_profile_context: boolean;
      items: Array<
        | components["schemas"]["DailyEventResponse"]
        | components["schemas"]["DailyObservationResponse"]
      >;
      next_cursor: string | null;
      profile_context_refs: Array<
        components["schemas"]["ProfileContextReference"]
      >;
      profile_context_truncated: boolean;
      summaries: Array<components["schemas"]["MetricSummaryV1"]>;
      timezone: string;
    };
    UTCInstant: string;
    WorkoutEventV1: {
      distance?: components["schemas"]["DistanceQuantity"] | null;
      duration?: components["schemas"]["DurationQuantity"] | null;
      kind: "workout";
      label: string;
    };
  };
}

export interface operations {
  archiveEvent: {
    path: {
      event_id: string;
    };
    query: {
      expected_revision: number;
    };
    responses: {
      "200": components["schemas"]["DailyEventResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "404": components["schemas"]["ErrorResponse"];
      "409": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  archiveObservation: {
    path: {
      observation_id: string;
    };
    query: {
      expected_revision: number;
    };
    responses: {
      "200": components["schemas"]["DailyObservationResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "404": components["schemas"]["ErrorResponse"];
      "409": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
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
  createDailyEntry: {
    requestBody: components["schemas"]["DailyEntryCreateRequest"];
    responses: {
      "200": components["schemas"]["DailyEntryCreateResponse"];
      "201": components["schemas"]["DailyEntryCreateResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "409": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  createEvent: {
    requestBody: components["schemas"]["DailyEventCreateRequest"];
    responses: {
      "200": components["schemas"]["DailyEventResponse"];
      "201": components["schemas"]["DailyEventResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "409": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  createObservation: {
    requestBody: components["schemas"]["DailyObservationCreateRequest"];
    responses: {
      "200": components["schemas"]["DailyObservationResponse"];
      "201": components["schemas"]["DailyObservationResponse"];
      "401": components["schemas"]["ErrorResponse"];
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
  getEvent: {
    path: {
      event_id: string;
    };
    responses: {
      "200": components["schemas"]["DailyEventResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "404": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  getObservation: {
    path: {
      observation_id: string;
    };
    responses: {
      "200": components["schemas"]["DailyObservationResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "404": components["schemas"]["ErrorResponse"];
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
  getToday: {
    query?: {
      date?: string | null;
      timezone?: string | null;
      limit?: number;
      cursor?: string | null;
    };
    responses: {
      "200": components["schemas"]["TodayResponse"];
      "401": components["schemas"]["ErrorResponse"];
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
  listEventHistory: {
    path: {
      event_id: string;
    };
    query?: {
      after_revision?: number;
      limit?: number;
    };
    responses: {
      "200": components["schemas"]["DailyHistoryResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "404": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  listEvents: {
    query?: {
      from_date?: string | null;
      to_date?: string | null;
      timezone?: string | null;
      limit?: number;
      cursor?: string | null;
    };
    responses: {
      "200": components["schemas"]["DailyEventListResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  listObservationHistory: {
    path: {
      observation_id: string;
    };
    query?: {
      after_revision?: number;
      limit?: number;
    };
    responses: {
      "200": components["schemas"]["DailyHistoryResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "404": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  listObservations: {
    query?: {
      from_date?: string | null;
      to_date?: string | null;
      timezone?: string | null;
      limit?: number;
      cursor?: string | null;
    };
    responses: {
      "200": components["schemas"]["DailyObservationListResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
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
  updateEvent: {
    path: {
      event_id: string;
    };
    requestBody: components["schemas"]["DailyEventUpdateRequest"];
    responses: {
      "200": components["schemas"]["DailyEventResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "404": components["schemas"]["ErrorResponse"];
      "409": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  updateObservation: {
    path: {
      observation_id: string;
    };
    requestBody: components["schemas"]["DailyObservationUpdateRequest"];
    responses: {
      "200": components["schemas"]["DailyObservationResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "404": components["schemas"]["ErrorResponse"];
      "409": components["schemas"]["ErrorResponse"];
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

export class HealthApiClient {
  private readonly baseUrl: string;
  private readonly fetcher: FetchLike;

  constructor(
    baseUrl: string,
    fetcher: FetchLike = globalThis.fetch as FetchLike,
  ) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.fetcher = fetcher;
  }

  async archiveEvent(
    path: operations["archiveEvent"]["path"],
    query: operations["archiveEvent"]["query"],
  ): Promise<components["schemas"]["DailyEventResponse"]> {
    return this.request<components["schemas"]["DailyEventResponse"]>(
      "DELETE",
      `/events/${encodeURIComponent(path.event_id)}`,
      query,
      undefined,
    );
  }

  async archiveObservation(
    path: operations["archiveObservation"]["path"],
    query: operations["archiveObservation"]["query"],
  ): Promise<components["schemas"]["DailyObservationResponse"]> {
    return this.request<components["schemas"]["DailyObservationResponse"]>(
      "DELETE",
      `/observations/${encodeURIComponent(path.observation_id)}`,
      query,
      undefined,
    );
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

  async createDailyEntry(
    requestBody: operations["createDailyEntry"]["requestBody"],
  ): Promise<components["schemas"]["DailyEntryCreateResponse"]> {
    return this.request<components["schemas"]["DailyEntryCreateResponse"]>(
      "POST",
      `/daily-entries`,
      undefined,
      requestBody,
    );
  }

  async createEvent(
    requestBody: operations["createEvent"]["requestBody"],
  ): Promise<components["schemas"]["DailyEventResponse"]> {
    return this.request<components["schemas"]["DailyEventResponse"]>(
      "POST",
      `/events`,
      undefined,
      requestBody,
    );
  }

  async createObservation(
    requestBody: operations["createObservation"]["requestBody"],
  ): Promise<components["schemas"]["DailyObservationResponse"]> {
    return this.request<components["schemas"]["DailyObservationResponse"]>(
      "POST",
      `/observations`,
      undefined,
      requestBody,
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

  async getEvent(
    path: operations["getEvent"]["path"],
  ): Promise<components["schemas"]["DailyEventResponse"]> {
    return this.request<components["schemas"]["DailyEventResponse"]>(
      "GET",
      `/events/${encodeURIComponent(path.event_id)}`,
      undefined,
      undefined,
    );
  }

  async getObservation(
    path: operations["getObservation"]["path"],
  ): Promise<components["schemas"]["DailyObservationResponse"]> {
    return this.request<components["schemas"]["DailyObservationResponse"]>(
      "GET",
      `/observations/${encodeURIComponent(path.observation_id)}`,
      undefined,
      undefined,
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

  async getToday(
    query?: operations["getToday"]["query"],
  ): Promise<components["schemas"]["TodayResponse"]> {
    return this.request<components["schemas"]["TodayResponse"]>(
      "GET",
      `/today`,
      query,
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

  async listEventHistory(
    path: operations["listEventHistory"]["path"],
    query?: operations["listEventHistory"]["query"],
  ): Promise<components["schemas"]["DailyHistoryResponse"]> {
    return this.request<components["schemas"]["DailyHistoryResponse"]>(
      "GET",
      `/events/${encodeURIComponent(path.event_id)}/history`,
      query,
      undefined,
    );
  }

  async listEvents(
    query?: operations["listEvents"]["query"],
  ): Promise<components["schemas"]["DailyEventListResponse"]> {
    return this.request<components["schemas"]["DailyEventListResponse"]>(
      "GET",
      `/events`,
      query,
      undefined,
    );
  }

  async listObservationHistory(
    path: operations["listObservationHistory"]["path"],
    query?: operations["listObservationHistory"]["query"],
  ): Promise<components["schemas"]["DailyHistoryResponse"]> {
    return this.request<components["schemas"]["DailyHistoryResponse"]>(
      "GET",
      `/observations/${encodeURIComponent(path.observation_id)}/history`,
      query,
      undefined,
    );
  }

  async listObservations(
    query?: operations["listObservations"]["query"],
  ): Promise<components["schemas"]["DailyObservationListResponse"]> {
    return this.request<components["schemas"]["DailyObservationListResponse"]>(
      "GET",
      `/observations`,
      query,
      undefined,
    );
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

  async updateEvent(
    path: operations["updateEvent"]["path"],
    requestBody: operations["updateEvent"]["requestBody"],
  ): Promise<components["schemas"]["DailyEventResponse"]> {
    return this.request<components["schemas"]["DailyEventResponse"]>(
      "PATCH",
      `/events/${encodeURIComponent(path.event_id)}`,
      undefined,
      requestBody,
    );
  }

  async updateObservation(
    path: operations["updateObservation"]["path"],
    requestBody: operations["updateObservation"]["requestBody"],
  ): Promise<components["schemas"]["DailyObservationResponse"]> {
    return this.request<components["schemas"]["DailyObservationResponse"]>(
      "PATCH",
      `/observations/${encodeURIComponent(path.observation_id)}`,
      undefined,
      requestBody,
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

export { HealthApiClient as ProfileApiClient };
