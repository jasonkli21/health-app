/* Generated from contracts/openapi/openapi.json. Do not edit by hand. */

export interface components {
  schemas: {
    AIContextEntry: {
      confirmation_status: components["schemas"]["ConfirmationStatus"];
      content: {
        [key: string]: unknown;
      };
      content_is_user_data: true;
      domain: string;
      object_id: string;
      object_type:
        | "profile_item"
        | "event"
        | "observation"
        | "goal"
        | "regimen"
        | "plan"
        | "context";
      relevance_reason: string;
      revision: number;
      source_kind:
        | "manual"
        | "device"
        | "document"
        | "provider"
        | "ai"
        | "system";
      title: string;
      valid_from: string | null;
      valid_to: string | null;
    };
    AIContextPack: {
      as_of: string;
      budget_bytes: 65536;
      built_at: string;
      domains: Array<string>;
      entries: Array<components["schemas"]["AIContextEntry"]>;
      included_counts: {
        [key: string]: number;
      };
      lookback_days: number;
      omitted_by_budget: number;
      omitted_by_user: number;
      owner_scope: string;
      request_id: string;
      resource_types: Array<
        | "profile_item"
        | "event"
        | "observation"
        | "goal"
        | "regimen"
        | "plan"
        | "context"
      >;
      schema_version: 1;
      sections: Array<"entries" | "today_summaries">;
      serialized_bytes: number;
      task: string;
      task_kind:
        | "general_wellness"
        | "education"
        | "understand_health_data"
        | "consequential_medical"
        | "urgent_safety";
      timezone: string;
      today_summaries: Array<components["schemas"]["MetricSummaryV1"]>;
      today_summary_date: string;
      today_summary_scope: "included_opted_in_entries_only";
      truncated: boolean;
    };
    AIContextRequest: {
      as_of?: string | null;
      domains?: Array<string>;
      excluded_object_ids?: Array<string>;
      lookback_days?: number;
      resource_types: Array<
        | "profile_item"
        | "event"
        | "observation"
        | "goal"
        | "regimen"
        | "plan"
        | "context"
      >;
      sections?: Array<"entries" | "today_summaries">;
      task: string;
      task_kind?:
        | "general_wellness"
        | "education"
        | "understand_health_data"
        | "consequential_medical"
        | "urgent_safety";
      timezone?: string | null;
    };
    AIEvidenceReference: {
      object_id: string;
      object_type?:
        | "profile_item"
        | "event"
        | "observation"
        | "goal"
        | "regimen"
        | "plan"
        | "context"
        | null;
      revision: number;
      title?: string | null;
    };
    AISearchResponse: {
      items: Array<components["schemas"]["AISearchResult"]>;
      next_cursor: string | null;
    };
    AISearchResult: {
      confirmation_status: components["schemas"]["ConfirmationStatus"];
      domain: string;
      excerpt: string;
      interval_end?: string | null;
      local_date?: string | null;
      object_id: string;
      object_type:
        | "profile_item"
        | "event"
        | "observation"
        | "goal"
        | "regimen"
        | "plan"
        | "context";
      occurred_at?: string | null;
      revision: number;
      source_kind:
        | "manual"
        | "device"
        | "document"
        | "provider"
        | "ai"
        | "system";
      time_precision?: "instant" | "date_only" | null;
      timezone?: string | null;
      title: string;
      valid_from?: string | null;
      valid_to?: string | null;
    };
    AssistantMessageRequest: {
      message: string;
      scope: components["schemas"]["AIContextRequest"];
    };
    AssistantMessageResponse: {
      context_summary: {
        [key: string]: number;
      };
      evidence_refs: Array<components["schemas"]["AIEvidenceReference"]>;
      reply: string;
      request_id: string;
      risk_class:
        | "general_wellness"
        | "education"
        | "understand_health_data"
        | "consequential_medical"
        | "urgent_safety";
      service_status: "complete";
    };
    AssistantStatusResponse: {
      adapter_status: "disabled" | "ready";
      allowed_capabilities: Array<
        | "health.context"
        | "health.search"
        | "health.today"
        | "health.profile"
        | "health.goals"
        | "health.plans"
      >;
      enabled: boolean;
      message: string;
    };
    BooleanValue: {
      type: "boolean";
      value: boolean;
    };
    ConfirmationStatus: "unconfirmed" | "user_confirmed";
    ContextCreateRequest: {
      ai_use_allowed?: boolean;
      context: components["schemas"]["ContextPayloadV1"];
      cross_domain_use_allowed?: boolean;
      id: string;
      notes?: string | null;
    };
    ContextLifecycle: "active" | "ended";
    ContextPayloadV1: {
      context_type: components["schemas"]["ContextType"];
      end_at?: string | null;
      label: string;
      notes?: string | null;
      priority?: number;
      related?: Array<components["schemas"]["ContextRelation"]>;
      start_at?: string | null;
    };
    ContextRelation: {
      object_id: string;
      priority?: number;
      relevance?: string;
    };
    ContextResponse: {
      ai_use_allowed: boolean;
      confirmation_status: components["schemas"]["ConfirmationStatus"];
      context: components["schemas"]["ContextPayloadV1"];
      created_at: string;
      cross_domain_use_allowed: boolean;
      domain: string;
      id: string;
      lifecycle: string;
      notes: string | null;
      object_type: "context";
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
    ContextType:
      | "travel"
      | "illness"
      | "recovery"
      | "schedule_change"
      | "other";
    ContextUpdateRequest: {
      ai_use_allowed?: boolean | null;
      context: components["schemas"]["ContextPayloadV1"];
      cross_domain_use_allowed?: boolean | null;
      expected_revision: number;
    };
    CoverageV1: {
      known_count: number;
      total_count: number;
    };
    CustomTrackerValueV1: {
      metric: "custom";
      schema_version: number;
      tracker_id: string;
      unit?: "custom";
      values: {
        [key: string]: unknown;
      };
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
      ai_use_allowed?: boolean;
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
      ai_use_allowed?: boolean;
      event: components["schemas"]["EventSchemaV1"];
      expected_revision: number;
    };
    DailyHistoryEntry: {
      actor_kind: "user";
      proposal_id?: string | null;
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
      ai_use_allowed?: boolean;
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
      ai_use_allowed?: boolean;
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
      value: components["schemas"]["FiniteDailyNumber"];
    };
    DurationQuantity: {
      unit: "min" | "h";
      value: components["schemas"]["FiniteDailyNumber"];
    };
    EnergyQuantity: {
      unit: "kcal" | "kJ";
      value: components["schemas"]["FiniteDailyNumber"];
    };
    EnteredQuantity: {
      unit: components["schemas"]["ProfileUnit"];
      value: components["schemas"]["FiniteDailyNumber"];
    };
    ErrorResponse: {
      code: string;
      field_errors?: Array<components["schemas"]["FieldError"]> | null;
      message: string;
      request_id: string;
    };
    EventCreateCommand: {
      action: "event.create";
      event: components["schemas"]["EventSchemaV1"];
      event_id: string;
      linked_observations?: Array<components["schemas"]["ObservationSchemaV1"]>;
      observation_ids?: Array<string>;
    };
    EventCreateDraft: {
      action: "event.create";
      event: components["schemas"]["EventSchemaV1"];
      linked_observations?: Array<components["schemas"]["ObservationSchemaV1"]>;
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
    EvidenceDetail: {
      object_id: string;
      object_type: string;
      revision: number;
      title: string;
    };
    EvidenceReference: {
      object_id: string;
      revision: number;
    };
    FieldError: {
      field: string;
      message: string;
    };
    FiniteDailyNumber: number;
    FiniteProfileNumber: number;
    GoalComparator: "at_least" | "at_most" | "equal";
    GoalCreateCommand: {
      action: "goal.create";
      goal: components["schemas"]["GoalPayloadV1"];
      id: string;
      notes?: string | null;
    };
    GoalCreateDraft: {
      action: "goal.create";
      goal: components["schemas"]["GoalPayloadV1"];
      notes?: string | null;
    };
    GoalCreateRequest: {
      ai_use_allowed?: boolean;
      cross_domain_use_allowed?: boolean;
      goal: components["schemas"]["GoalPayloadV1"];
      id: string;
      notes?: string | null;
    };
    GoalDomain:
      | "nutrition"
      | "exercise"
      | "sleep"
      | "symptoms"
      | "measurements"
      | "general";
    GoalLifecycle: "active" | "paused" | "completed";
    GoalPayloadV1: {
      domain: components["schemas"]["GoalDomain"];
      label: string;
      start_date?: string | null;
      target?: components["schemas"]["MetricTarget"] | null;
      target_date?: string | null;
      target_period?: "day" | "week" | "month" | "year" | "once" | null;
    };
    GoalResponse: {
      ai_use_allowed: boolean;
      confirmation_status: components["schemas"]["ConfirmationStatus"];
      created_at: string;
      cross_domain_use_allowed: boolean;
      domain: string;
      goal: components["schemas"]["GoalPayloadV1"];
      id: string;
      lifecycle: string;
      notes: string | null;
      object_type: "goal";
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
    GoalUpdateCommand: {
      action: "goal.update";
      expected_revision: number;
      goal: components["schemas"]["GoalPayloadV1"];
      object_id: string;
    };
    GoalUpdateRequest: {
      ai_use_allowed?: boolean | null;
      cross_domain_use_allowed?: boolean | null;
      expected_revision: number;
      goal: components["schemas"]["GoalPayloadV1"];
    };
    InstantTimePoint: {
      occurred_at: components["schemas"]["UTCInstant"];
      precision: "instant";
      timezone: string;
    };
    LifecycleUpdateRequest: {
      ai_use_allowed?: boolean | null;
      cross_domain_use_allowed?: boolean | null;
      expected_revision: number;
      lifecycle:
        | components["schemas"]["GoalLifecycle"]
        | components["schemas"]["RegimenLifecycle"]
        | components["schemas"]["PlanLifecycle"]
        | components["schemas"]["ContextLifecycle"];
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
      value: components["schemas"]["FiniteDailyNumber"];
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
    MetricTarget: {
      comparator: components["schemas"]["GoalComparator"];
      metric: components["schemas"]["MetricKey"];
      unit: components["schemas"]["MeasurementUnit"];
      value: components["schemas"]["FiniteDailyNumber"];
    };
    NumberValue: {
      type: "number";
      value: components["schemas"]["FiniteProfileNumber"];
    };
    ObservationPayloadV1: {
      value: components["schemas"]["ObservationValueV1"];
    };
    ObservationSchemaV1: {
      domain: components["schemas"]["DailyDomain"];
      interval_end?: components["schemas"]["UTCInstant"] | null;
      notes?: string | null;
      payload: components["schemas"]["ObservationPayloadV1"];
      time: components["schemas"]["DailyTimePoint"];
    };
    ObservationValueV1:
      | components["schemas"]["MeasurementValueV1"]
      | components["schemas"]["SymptomSeverityV1"]
      | components["schemas"]["CustomTrackerValueV1"];
    OccurrenceActionRequest: {
      expected_override_revision?: number | null;
      expected_schedule_revision: number;
      linked_event_id?: string | null;
      linked_observation_id?: string | null;
      rescheduled_at?: string | null;
      state: "completed" | "skipped" | "rescheduled";
    };
    OccurrenceActionResponse: {
      key: string;
      linked_event_id: string | null;
      linked_observation_id?: string | null;
      override_revision: number;
      rescheduled_at: string | null;
      schedule_revision: number;
      state: "completed" | "skipped" | "rescheduled";
      updated_at: string;
    };
    OccurrenceHistoryEntry: {
      acted_at: string;
      action: "completed" | "skipped" | "rescheduled";
      linked_event_id: string | null;
      linked_observation_id: string | null;
      rescheduled_at: string | null;
      revision: number;
      schedule_revision: number;
    };
    OccurrenceHistoryResponse: {
      items: Array<components["schemas"]["OccurrenceHistoryEntry"]>;
      next_after_revision: number | null;
    };
    OccurrenceListResponse: {
      items: Array<components["schemas"]["OccurrenceResponse"]>;
    };
    OccurrenceResponse: {
      can_act?: boolean;
      dst_resolution: "exact" | "earlier_offset" | "next_valid_time";
      due_at: string;
      item_id: string | null;
      key: string;
      label: string;
      linked_event_id: string | null;
      linked_observation_id?: string | null;
      original_local_date: string;
      original_local_time: string;
      override_revision: number | null;
      parent_id: string;
      schedule_id: string;
      schedule_revision: number;
      state: "unknown" | "completed" | "skipped" | "rescheduled";
      timezone: string;
    };
    PlanCreateCommand: {
      action: "plan.create";
      id: string;
      notes?: string | null;
      plan: components["schemas"]["PlanPayloadV1"];
    };
    PlanCreateDraft: {
      action: "plan.create";
      notes?: string | null;
      plan: components["schemas"]["PlanPayloadV1"];
    };
    PlanCreateRequest: {
      ai_use_allowed?: boolean;
      cross_domain_use_allowed?: boolean;
      id: string;
      notes?: string | null;
      plan: components["schemas"]["PlanPayloadV1"];
    };
    PlanItemInput: {
      id: string;
      kind: components["schemas"]["PlanItemKind"];
      label: string;
      reference_id?: string | null;
    };
    PlanItemKind: "goal" | "regimen" | "task";
    PlanLifecycle: "active" | "paused" | "completed";
    PlanningHistoryEntry: {
      actor_kind: "user";
      proposal_id?: string | null;
      reason: "create" | "update" | "archive";
      recorded_at: string;
      revision: number;
      snapshot: {
        [key: string]: unknown;
      };
    };
    PlanningHistoryResponse: {
      items: Array<components["schemas"]["PlanningHistoryEntry"]>;
      next_after_revision: number | null;
    };
    PlanningListResponse: {
      items: Array<
        | components["schemas"]["GoalResponse"]
        | components["schemas"]["RegimenResponse"]
        | components["schemas"]["PlanResponse"]
        | components["schemas"]["ContextResponse"]
        | components["schemas"]["TrackerResponse"]
      >;
      next_cursor: string | null;
    };
    PlanOrderRequest: {
      ai_use_allowed?: boolean | null;
      cross_domain_use_allowed?: boolean | null;
      expected_revision: number;
      item_ids: Array<string>;
    };
    PlanPayloadV1: {
      end_date?: string | null;
      items?: Array<components["schemas"]["PlanItemInput"]>;
      label: string;
      start_date?: string | null;
    };
    PlanResponse: {
      ai_use_allowed: boolean;
      confirmation_status: components["schemas"]["ConfirmationStatus"];
      created_at: string;
      cross_domain_use_allowed: boolean;
      domain: string;
      id: string;
      lifecycle: string;
      notes: string | null;
      object_type: "plan";
      plan: components["schemas"]["PlanPayloadV1"];
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
    PlanUpdateCommand: {
      action: "plan.update";
      expected_revision: number;
      object_id: string;
      plan: components["schemas"]["PlanPayloadV1"];
    };
    PlanUpdateRequest: {
      ai_use_allowed?: boolean | null;
      cross_domain_use_allowed?: boolean | null;
      expected_revision: number;
      plan: components["schemas"]["PlanPayloadV1"];
    };
    ProfileCategory: "background" | "constraints" | "preferences";
    ProfileContextReference: {
      id: string;
      title: string;
    };
    ProfileCreateCommand: {
      action: "profile.create";
      id: string;
      metadata?: components["schemas"]["ProfileMetadata"];
      notes?: string | null;
      profile: components["schemas"]["ProfilePayloadV1"];
      valid_from?: string | null;
      valid_to?: string | null;
    };
    ProfileCreateDraft: {
      action: "profile.create";
      metadata?: components["schemas"]["ProfileMetadata"];
      notes?: string | null;
      profile: components["schemas"]["ProfilePayloadV1"];
      valid_from?: string | null;
      valid_to?: string | null;
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
      proposal_id?: string | null;
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
    ProfileUpdateCommand: {
      action: "profile.update";
      expected_revision: number;
      metadata?: components["schemas"]["ProfileMetadata"] | null;
      notes?: string | null;
      object_id: string;
      profile: components["schemas"]["ProfilePayloadV1"];
      valid_from?: string | null;
      valid_to?: string | null;
    };
    ProfileValue:
      | components["schemas"]["TextValue"]
      | components["schemas"]["BooleanValue"]
      | components["schemas"]["NumberValue"]
      | components["schemas"]["QuantityValue"]
      | components["schemas"]["TextListValue"];
    ProposalApplyRequest: {
      confirmation: "explicit_user_save";
      content_hash: string;
      idempotency_key: string;
      proposal_revision: number;
    };
    ProposalApplyResponse: {
      proposal: components["schemas"]["ProposalState"];
      replayed?: boolean;
    };
    ProposalCommand:
      | components["schemas"]["ProfileCreateCommand"]
      | components["schemas"]["ProfileUpdateCommand"]
      | components["schemas"]["EventCreateCommand"]
      | components["schemas"]["GoalCreateCommand"]
      | components["schemas"]["GoalUpdateCommand"]
      | components["schemas"]["PlanCreateCommand"]
      | components["schemas"]["PlanUpdateCommand"]
      | components["schemas"]["TrackerCreateCommand"];
    ProposalCreateRequest: {
      commands: Array<components["schemas"]["ProposalDraftCommand"]>;
      evidence_refs?: Array<components["schemas"]["EvidenceReference"]>;
      id: string;
      rationale?: string;
    };
    ProposalDraftCommand:
      | components["schemas"]["ProfileCreateDraft"]
      | components["schemas"]["ProfileUpdateCommand"]
      | components["schemas"]["EventCreateDraft"]
      | components["schemas"]["GoalCreateDraft"]
      | components["schemas"]["GoalUpdateCommand"]
      | components["schemas"]["PlanCreateDraft"]
      | components["schemas"]["PlanUpdateCommand"]
      | components["schemas"]["TrackerCreateDraft"];
    ProposalEditRequest: {
      commands: Array<components["schemas"]["ProposalDraftCommand"]>;
      evidence_refs?: Array<components["schemas"]["EvidenceReference"]>;
      expected_revision: number;
      rationale?: string;
    };
    ProposalHistoryEntry: {
      actor_id: string;
      details?: {
        [key: string]: unknown;
      };
      event: "created" | "edited" | "applied" | "rejected" | "expired";
      proposal_revision: number;
      recorded_at: string;
    };
    ProposalHistoryResponse: {
      items: Array<components["schemas"]["ProposalHistoryEntry"]>;
      next_cursor?: string | null;
    };
    ProposalListResponse: {
      items: Array<components["schemas"]["ProposalState"]>;
      next_cursor: string | null;
    };
    ProposalRejectRequest: {
      proposal_revision: number;
      reason?: string | null;
    };
    ProposalResult: {
      object_id: string;
      object_type:
        | "profile_item"
        | "event"
        | "observation"
        | "goal"
        | "plan"
        | "tracker_definition";
      revision: number;
    };
    ProposalState: {
      applied_at?: string | null;
      commands: Array<components["schemas"]["ProposalCommand"]>;
      confirmed_at?: string | null;
      confirmed_by?: string | null;
      content_hash: string;
      created_at: string;
      evidence_refs: Array<components["schemas"]["EvidenceDetail"]>;
      expires_at: string;
      id: string;
      last_validation_summary?: {
        [key: string]: unknown;
      };
      origin: "user" | "ai";
      rationale: string;
      reject_reason?: string | null;
      rejected_at?: string | null;
      rejected_by?: string | null;
      results?: Array<components["schemas"]["ProposalResult"]>;
      revision: number;
      schema_version?: 1;
      state: "pending" | "applied" | "rejected" | "expired" | "superseded";
      updated_at: string;
    };
    QuantityValue: {
      type: "quantity";
      unit: components["schemas"]["ProfileUnit"];
      value: components["schemas"]["FiniteProfileNumber"];
    };
    RegimenCreateRequest: {
      ai_use_allowed?: boolean;
      cross_domain_use_allowed?: boolean;
      id: string;
      notes?: string | null;
      regimen: components["schemas"]["RegimenPayloadV1"];
    };
    RegimenKind: "habit" | "medication" | "supplement" | "activity";
    RegimenLifecycle: "active" | "paused" | "completed";
    RegimenPayloadV1: {
      domain?: components["schemas"]["GoalDomain"];
      end_date?: string | null;
      instructions?: string | null;
      kind: components["schemas"]["RegimenKind"];
      label: string;
      quantity?: components["schemas"]["EnteredQuantity"] | null;
      start_date?: string | null;
    };
    RegimenResponse: {
      ai_use_allowed: boolean;
      confirmation_status: components["schemas"]["ConfirmationStatus"];
      created_at: string;
      cross_domain_use_allowed: boolean;
      domain: string;
      id: string;
      lifecycle: string;
      notes: string | null;
      object_type: "regimen";
      recorded_at: string;
      regimen: components["schemas"]["RegimenPayloadV1"];
      revision: number;
      schema_version: 1;
      source: components["schemas"]["ProfileSource"];
      status: "active" | "archived";
      title: string;
      updated_at: string;
      valid_from: string | null;
      valid_to: string | null;
    };
    RegimenUpdateRequest: {
      ai_use_allowed?: boolean | null;
      cross_domain_use_allowed?: boolean | null;
      expected_revision: number;
      regimen: components["schemas"]["RegimenPayloadV1"];
    };
    ScheduleDefinitionV1: {
      end_date?: string | null;
      interval?: number;
      local_time: string;
      recurrence: components["schemas"]["ScheduleRecurrence"];
      start_date: string;
      timezone: string;
      weekdays?: Array<number>;
    };
    ScheduleEditRequest: {
      effective_from: string;
      expected_schedule_revision?: number | null;
      schedule: components["schemas"]["ScheduleDefinitionV1"];
    };
    ScheduleRecurrence: "daily" | "weekly";
    ScheduleResponse: {
      effective_from: string;
      schedule: components["schemas"]["ScheduleDefinitionV1"];
      schedule_id: string;
      schedule_revision: number;
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
    TodayContextSummary: {
      context_type: components["schemas"]["ContextType"];
      id: string;
      label: string;
      notes: string | null;
      priority: number;
      related: Array<components["schemas"]["ContextRelation"]>;
    };
    TodayResponse: {
      active_contexts?: Array<components["schemas"]["TodayContextSummary"]>;
      as_of_sequence: number;
      date: string;
      includes_profile_context: boolean;
      items: Array<
        | components["schemas"]["DailyEventResponse"]
        | components["schemas"]["DailyObservationResponse"]
      >;
      next_cursor: string | null;
      plan_items?: Array<components["schemas"]["OccurrenceResponse"]>;
      profile_context_refs: Array<
        components["schemas"]["ProfileContextReference"]
      >;
      profile_context_truncated: boolean;
      summaries: Array<components["schemas"]["MetricSummaryV1"]>;
      timezone: string;
    };
    TrackerCreateCommand: {
      action: "tracker.create";
      definition: components["schemas"]["TrackerDefinitionV1"];
      id: string;
      notes?: string | null;
    };
    TrackerCreateDraft: {
      action: "tracker.create";
      definition: components["schemas"]["TrackerDefinitionV1"];
      notes?: string | null;
    };
    TrackerCreateRequest: {
      ai_use_allowed?: boolean;
      cross_domain_use_allowed?: boolean;
      definition: components["schemas"]["TrackerDefinitionV1"];
      id: string;
      notes?: string | null;
    };
    TrackerDefinitionV1: {
      domain: components["schemas"]["DailyDomain"];
      fields: Array<components["schemas"]["TrackerFieldV1"]>;
      name: string;
    };
    TrackerFieldKind:
      | "text"
      | "number"
      | "boolean"
      | "enum"
      | "date"
      | "quantity";
    TrackerFieldV1: {
      choices?: Array<string>;
      id: string;
      kind: components["schemas"]["TrackerFieldKind"];
      label: string;
      required?: boolean;
      unit?: components["schemas"]["ProfileUnit"] | null;
    };
    TrackerResponse: {
      ai_use_allowed: boolean;
      confirmation_status: components["schemas"]["ConfirmationStatus"];
      created_at: string;
      cross_domain_use_allowed: boolean;
      current_schema_version: number;
      definition: components["schemas"]["TrackerDefinitionV1"];
      domain: string;
      id: string;
      lifecycle: string;
      notes: string | null;
      object_type: "tracker_definition";
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
    TrackerSchemaVersionListResponse: {
      items: Array<components["schemas"]["TrackerSchemaVersionResponse"]>;
      next_after_version: number | null;
    };
    TrackerSchemaVersionResponse: {
      created_at: string;
      definition: components["schemas"]["TrackerDefinitionV1"];
      version: number;
    };
    TrackerUpdateRequest: {
      ai_use_allowed?: boolean | null;
      cross_domain_use_allowed?: boolean | null;
      definition: components["schemas"]["TrackerDefinitionV1"];
      expected_revision: number;
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
  applyActionProposal: {
    path: {
      proposal_id: string;
    };
    requestBody: components["schemas"]["ProposalApplyRequest"];
    responses: {
      "200": components["schemas"]["ProposalApplyResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "404": components["schemas"]["ErrorResponse"];
      "409": components["schemas"]["ErrorResponse"];
      "410": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  archiveContext: {
    path: {
      context_id: string;
    };
    query: {
      expected_revision: number;
    };
    responses: {
      "200": components["schemas"]["ContextResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
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
  archiveGoal: {
    path: {
      goal_id: string;
    };
    query: {
      expected_revision: number;
    };
    responses: {
      "200": components["schemas"]["GoalResponse"];
      "401": components["schemas"]["ErrorResponse"];
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
  archivePlan: {
    path: {
      plan_id: string;
    };
    query: {
      expected_revision: number;
    };
    responses: {
      "200": components["schemas"]["PlanResponse"];
      "401": components["schemas"]["ErrorResponse"];
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
  archiveRegimen: {
    path: {
      regimen_id: string;
    };
    query: {
      expected_revision: number;
    };
    responses: {
      "200": components["schemas"]["RegimenResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  archiveTracker: {
    path: {
      tracker_id: string;
    };
    query: {
      expected_revision: number;
    };
    responses: {
      "200": components["schemas"]["TrackerResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  createActionProposal: {
    requestBody: components["schemas"]["ProposalCreateRequest"];
    responses: {
      "200": components["schemas"]["ProposalState"];
      "201": components["schemas"]["ProposalState"];
      "401": components["schemas"]["ErrorResponse"];
      "404": components["schemas"]["ErrorResponse"];
      "409": components["schemas"]["ErrorResponse"];
      "410": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  createContext: {
    requestBody: components["schemas"]["ContextCreateRequest"];
    responses: {
      "201": components["schemas"]["ContextResponse"];
      "401": components["schemas"]["ErrorResponse"];
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
  createGoal: {
    requestBody: components["schemas"]["GoalCreateRequest"];
    responses: {
      "201": components["schemas"]["GoalResponse"];
      "401": components["schemas"]["ErrorResponse"];
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
  createPlan: {
    requestBody: components["schemas"]["PlanCreateRequest"];
    responses: {
      "201": components["schemas"]["PlanResponse"];
      "401": components["schemas"]["ErrorResponse"];
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
  createRegimen: {
    requestBody: components["schemas"]["RegimenCreateRequest"];
    responses: {
      "201": components["schemas"]["RegimenResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  createTracker: {
    requestBody: components["schemas"]["TrackerCreateRequest"];
    responses: {
      "201": components["schemas"]["TrackerResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  editActionProposal: {
    path: {
      proposal_id: string;
    };
    requestBody: components["schemas"]["ProposalEditRequest"];
    responses: {
      "200": components["schemas"]["ProposalState"];
      "401": components["schemas"]["ErrorResponse"];
      "404": components["schemas"]["ErrorResponse"];
      "409": components["schemas"]["ErrorResponse"];
      "410": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  editPlanItemSchedule: {
    path: {
      plan_id: string;
      item_id: string;
    };
    requestBody: components["schemas"]["ScheduleEditRequest"];
    responses: {
      "200": components["schemas"]["ScheduleResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  editRegimenSchedule: {
    path: {
      regimen_id: string;
    };
    requestBody: components["schemas"]["ScheduleEditRequest"];
    responses: {
      "200": components["schemas"]["ScheduleResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  getActionProposal: {
    path: {
      proposal_id: string;
    };
    responses: {
      "200": components["schemas"]["ProposalState"];
      "401": components["schemas"]["ErrorResponse"];
      "404": components["schemas"]["ErrorResponse"];
      "409": components["schemas"]["ErrorResponse"];
      "410": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  getAssistantStatus: {
    responses: {
      "200": components["schemas"]["AssistantStatusResponse"];
      "401": components["schemas"]["ErrorResponse"];
    };
  };
  getContext: {
    path: {
      context_id: string;
    };
    responses: {
      "200": components["schemas"]["ContextResponse"];
      "401": components["schemas"]["ErrorResponse"];
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
  getGoal: {
    path: {
      goal_id: string;
    };
    responses: {
      "200": components["schemas"]["GoalResponse"];
      "401": components["schemas"]["ErrorResponse"];
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
  getPlan: {
    path: {
      plan_id: string;
    };
    responses: {
      "200": components["schemas"]["PlanResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  getPlanItemSchedule: {
    path: {
      plan_id: string;
      item_id: string;
    };
    responses: {
      "200": components["schemas"]["ScheduleResponse"] | null;
      "401": components["schemas"]["ErrorResponse"];
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
  getRegimen: {
    path: {
      regimen_id: string;
    };
    responses: {
      "200": components["schemas"]["RegimenResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  getRegimenSchedule: {
    path: {
      regimen_id: string;
    };
    responses: {
      "200": components["schemas"]["ScheduleResponse"] | null;
      "401": components["schemas"]["ErrorResponse"];
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
  getTracker: {
    path: {
      tracker_id: string;
    };
    responses: {
      "200": components["schemas"]["TrackerResponse"];
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
  listActionProposalHistory: {
    path: {
      proposal_id: string;
    };
    query?: {
      limit?: number;
      cursor?: string | null;
    };
    responses: {
      "200": components["schemas"]["ProposalHistoryResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "404": components["schemas"]["ErrorResponse"];
      "409": components["schemas"]["ErrorResponse"];
      "410": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  listActionProposals: {
    query?: {
      state?:
        | "pending"
        | "applied"
        | "rejected"
        | "expired"
        | "superseded"
        | null;
      limit?: number;
      cursor?: string | null;
    };
    responses: {
      "200": components["schemas"]["ProposalListResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "404": components["schemas"]["ErrorResponse"];
      "409": components["schemas"]["ErrorResponse"];
      "410": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  listContextHistory: {
    path: {
      context_id: string;
    };
    query?: {
      after_revision?: number;
      limit?: number;
    };
    responses: {
      "200": components["schemas"]["PlanningHistoryResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  listContexts: {
    query?: {
      limit?: number;
      lifecycle?: components["schemas"]["ContextLifecycle"] | null;
      cursor?: string | null;
      archived?: boolean;
    };
    responses: {
      "200": components["schemas"]["PlanningListResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
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
  listGoalHistory: {
    path: {
      goal_id: string;
    };
    query?: {
      after_revision?: number;
      limit?: number;
    };
    responses: {
      "200": components["schemas"]["PlanningHistoryResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  listGoals: {
    query?: {
      limit?: number;
      lifecycle?: components["schemas"]["GoalLifecycle"] | null;
      cursor?: string | null;
      archived?: boolean;
    };
    responses: {
      "200": components["schemas"]["PlanningListResponse"];
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
  listPlanHistory: {
    path: {
      plan_id: string;
    };
    query?: {
      after_revision?: number;
      limit?: number;
    };
    responses: {
      "200": components["schemas"]["PlanningHistoryResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  listPlanOccurrenceHistory: {
    path: {
      occurrence_key: string;
    };
    query?: {
      after_revision?: number;
      limit?: number;
    };
    responses: {
      "200": components["schemas"]["OccurrenceHistoryResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  listPlanOccurrences: {
    path: {
      plan_id: string;
    };
    query: {
      start_date: string;
      end_date: string;
      timezone: string;
    };
    responses: {
      "200": components["schemas"]["OccurrenceListResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  listPlans: {
    query?: {
      limit?: number;
      lifecycle?: components["schemas"]["PlanLifecycle"] | null;
      cursor?: string | null;
      archived?: boolean;
    };
    responses: {
      "200": components["schemas"]["PlanningListResponse"];
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
  listRegimenHistory: {
    path: {
      regimen_id: string;
    };
    query?: {
      after_revision?: number;
      limit?: number;
    };
    responses: {
      "200": components["schemas"]["PlanningHistoryResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  listRegimenOccurrences: {
    path: {
      regimen_id: string;
    };
    query: {
      start_date: string;
      end_date: string;
      timezone: string;
    };
    responses: {
      "200": components["schemas"]["OccurrenceListResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  listRegimens: {
    query?: {
      limit?: number;
      lifecycle?: components["schemas"]["RegimenLifecycle"] | null;
      cursor?: string | null;
      archived?: boolean;
    };
    responses: {
      "200": components["schemas"]["PlanningListResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  listTrackerHistory: {
    path: {
      tracker_id: string;
    };
    query?: {
      after_revision?: number;
      limit?: number;
    };
    responses: {
      "200": components["schemas"]["PlanningHistoryResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  listTrackers: {
    query?: {
      limit?: number;
      cursor?: string | null;
      archived?: boolean;
    };
    responses: {
      "200": components["schemas"]["PlanningListResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  listTrackerVersions: {
    path: {
      tracker_id: string;
    };
    query?: {
      after_version?: number;
      limit?: number;
    };
    responses: {
      "200": components["schemas"]["TrackerSchemaVersionListResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  previewAIContext: {
    requestBody: components["schemas"]["AIContextRequest"];
    responses: {
      "200": components["schemas"]["AIContextPack"];
      "401": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  rejectActionProposal: {
    path: {
      proposal_id: string;
    };
    requestBody: components["schemas"]["ProposalRejectRequest"];
    responses: {
      "200": components["schemas"]["ProposalState"];
      "401": components["schemas"]["ErrorResponse"];
      "404": components["schemas"]["ErrorResponse"];
      "409": components["schemas"]["ErrorResponse"];
      "410": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  reorderPlanItems: {
    path: {
      plan_id: string;
    };
    requestBody: components["schemas"]["PlanOrderRequest"];
    responses: {
      "200": components["schemas"]["PlanResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  searchAIEligibleHealthData: {
    query: {
      q: string;
      types?: string | null;
      limit?: number;
      cursor?: string | null;
    };
    responses: {
      "200": components["schemas"]["AISearchResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  sendAssistantMessage: {
    requestBody: components["schemas"]["AssistantMessageRequest"];
    responses: {
      "200": components["schemas"]["AssistantMessageResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  transitionContext: {
    path: {
      context_id: string;
    };
    requestBody: components["schemas"]["LifecycleUpdateRequest"];
    responses: {
      "200": components["schemas"]["ContextResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  transitionGoal: {
    path: {
      goal_id: string;
    };
    requestBody: components["schemas"]["LifecycleUpdateRequest"];
    responses: {
      "200": components["schemas"]["GoalResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  transitionPlan: {
    path: {
      plan_id: string;
    };
    requestBody: components["schemas"]["LifecycleUpdateRequest"];
    responses: {
      "200": components["schemas"]["PlanResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  transitionRegimen: {
    path: {
      regimen_id: string;
    };
    requestBody: components["schemas"]["LifecycleUpdateRequest"];
    responses: {
      "200": components["schemas"]["RegimenResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  updateContext: {
    path: {
      context_id: string;
    };
    requestBody: components["schemas"]["ContextUpdateRequest"];
    responses: {
      "200": components["schemas"]["ContextResponse"];
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
  updateGoal: {
    path: {
      goal_id: string;
    };
    requestBody: components["schemas"]["GoalUpdateRequest"];
    responses: {
      "200": components["schemas"]["GoalResponse"];
      "401": components["schemas"]["ErrorResponse"];
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
  updatePlan: {
    path: {
      plan_id: string;
    };
    requestBody: components["schemas"]["PlanUpdateRequest"];
    responses: {
      "200": components["schemas"]["PlanResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  updatePlanOccurrence: {
    path: {
      occurrence_key: string;
    };
    requestBody: components["schemas"]["OccurrenceActionRequest"];
    responses: {
      "200": components["schemas"]["OccurrenceActionResponse"];
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
  updateRegimen: {
    path: {
      regimen_id: string;
    };
    requestBody: components["schemas"]["RegimenUpdateRequest"];
    responses: {
      "200": components["schemas"]["RegimenResponse"];
      "401": components["schemas"]["ErrorResponse"];
      "413": components["schemas"]["ErrorResponse"];
      "422": components["schemas"]["ErrorResponse"];
      "503": components["schemas"]["ErrorResponse"];
    };
  };
  updateTracker: {
    path: {
      tracker_id: string;
    };
    requestBody: components["schemas"]["TrackerUpdateRequest"];
    responses: {
      "200": components["schemas"]["TrackerResponse"];
      "401": components["schemas"]["ErrorResponse"];
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

  async applyActionProposal(
    path: operations["applyActionProposal"]["path"],
    requestBody: operations["applyActionProposal"]["requestBody"],
  ): Promise<components["schemas"]["ProposalApplyResponse"]> {
    return this.request<components["schemas"]["ProposalApplyResponse"]>(
      "POST",
      `/action-proposals/${encodeURIComponent(path.proposal_id)}/apply`,
      undefined,
      requestBody,
    );
  }

  async archiveContext(
    path: operations["archiveContext"]["path"],
    query: operations["archiveContext"]["query"],
  ): Promise<components["schemas"]["ContextResponse"]> {
    return this.request<components["schemas"]["ContextResponse"]>(
      "DELETE",
      `/contexts/${encodeURIComponent(path.context_id)}`,
      query,
      undefined,
    );
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

  async archiveGoal(
    path: operations["archiveGoal"]["path"],
    query: operations["archiveGoal"]["query"],
  ): Promise<components["schemas"]["GoalResponse"]> {
    return this.request<components["schemas"]["GoalResponse"]>(
      "DELETE",
      `/goals/${encodeURIComponent(path.goal_id)}`,
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

  async archivePlan(
    path: operations["archivePlan"]["path"],
    query: operations["archivePlan"]["query"],
  ): Promise<components["schemas"]["PlanResponse"]> {
    return this.request<components["schemas"]["PlanResponse"]>(
      "DELETE",
      `/plans/${encodeURIComponent(path.plan_id)}`,
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

  async archiveRegimen(
    path: operations["archiveRegimen"]["path"],
    query: operations["archiveRegimen"]["query"],
  ): Promise<components["schemas"]["RegimenResponse"]> {
    return this.request<components["schemas"]["RegimenResponse"]>(
      "DELETE",
      `/regimens/${encodeURIComponent(path.regimen_id)}`,
      query,
      undefined,
    );
  }

  async archiveTracker(
    path: operations["archiveTracker"]["path"],
    query: operations["archiveTracker"]["query"],
  ): Promise<components["schemas"]["TrackerResponse"]> {
    return this.request<components["schemas"]["TrackerResponse"]>(
      "DELETE",
      `/trackers/${encodeURIComponent(path.tracker_id)}`,
      query,
      undefined,
    );
  }

  async createActionProposal(
    requestBody: operations["createActionProposal"]["requestBody"],
  ): Promise<components["schemas"]["ProposalState"]> {
    return this.request<components["schemas"]["ProposalState"]>(
      "POST",
      `/action-proposals`,
      undefined,
      requestBody,
    );
  }

  async createContext(
    requestBody: operations["createContext"]["requestBody"],
  ): Promise<components["schemas"]["ContextResponse"]> {
    return this.request<components["schemas"]["ContextResponse"]>(
      "POST",
      `/contexts`,
      undefined,
      requestBody,
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

  async createGoal(
    requestBody: operations["createGoal"]["requestBody"],
  ): Promise<components["schemas"]["GoalResponse"]> {
    return this.request<components["schemas"]["GoalResponse"]>(
      "POST",
      `/goals`,
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

  async createPlan(
    requestBody: operations["createPlan"]["requestBody"],
  ): Promise<components["schemas"]["PlanResponse"]> {
    return this.request<components["schemas"]["PlanResponse"]>(
      "POST",
      `/plans`,
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

  async createRegimen(
    requestBody: operations["createRegimen"]["requestBody"],
  ): Promise<components["schemas"]["RegimenResponse"]> {
    return this.request<components["schemas"]["RegimenResponse"]>(
      "POST",
      `/regimens`,
      undefined,
      requestBody,
    );
  }

  async createTracker(
    requestBody: operations["createTracker"]["requestBody"],
  ): Promise<components["schemas"]["TrackerResponse"]> {
    return this.request<components["schemas"]["TrackerResponse"]>(
      "POST",
      `/trackers`,
      undefined,
      requestBody,
    );
  }

  async editActionProposal(
    path: operations["editActionProposal"]["path"],
    requestBody: operations["editActionProposal"]["requestBody"],
  ): Promise<components["schemas"]["ProposalState"]> {
    return this.request<components["schemas"]["ProposalState"]>(
      "PATCH",
      `/action-proposals/${encodeURIComponent(path.proposal_id)}`,
      undefined,
      requestBody,
    );
  }

  async editPlanItemSchedule(
    path: operations["editPlanItemSchedule"]["path"],
    requestBody: operations["editPlanItemSchedule"]["requestBody"],
  ): Promise<components["schemas"]["ScheduleResponse"]> {
    return this.request<components["schemas"]["ScheduleResponse"]>(
      "PUT",
      `/plans/${encodeURIComponent(path.plan_id)}/items/${encodeURIComponent(path.item_id)}/schedule`,
      undefined,
      requestBody,
    );
  }

  async editRegimenSchedule(
    path: operations["editRegimenSchedule"]["path"],
    requestBody: operations["editRegimenSchedule"]["requestBody"],
  ): Promise<components["schemas"]["ScheduleResponse"]> {
    return this.request<components["schemas"]["ScheduleResponse"]>(
      "PUT",
      `/regimens/${encodeURIComponent(path.regimen_id)}/schedule`,
      undefined,
      requestBody,
    );
  }

  async getActionProposal(
    path: operations["getActionProposal"]["path"],
  ): Promise<components["schemas"]["ProposalState"]> {
    return this.request<components["schemas"]["ProposalState"]>(
      "GET",
      `/action-proposals/${encodeURIComponent(path.proposal_id)}`,
      undefined,
      undefined,
    );
  }

  async getAssistantStatus(): Promise<
    components["schemas"]["AssistantStatusResponse"]
  > {
    return this.request<components["schemas"]["AssistantStatusResponse"]>(
      "GET",
      `/assistant/status`,
      undefined,
      undefined,
    );
  }

  async getContext(
    path: operations["getContext"]["path"],
  ): Promise<components["schemas"]["ContextResponse"]> {
    return this.request<components["schemas"]["ContextResponse"]>(
      "GET",
      `/contexts/${encodeURIComponent(path.context_id)}`,
      undefined,
      undefined,
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

  async getGoal(
    path: operations["getGoal"]["path"],
  ): Promise<components["schemas"]["GoalResponse"]> {
    return this.request<components["schemas"]["GoalResponse"]>(
      "GET",
      `/goals/${encodeURIComponent(path.goal_id)}`,
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

  async getPlan(
    path: operations["getPlan"]["path"],
  ): Promise<components["schemas"]["PlanResponse"]> {
    return this.request<components["schemas"]["PlanResponse"]>(
      "GET",
      `/plans/${encodeURIComponent(path.plan_id)}`,
      undefined,
      undefined,
    );
  }

  async getPlanItemSchedule(
    path: operations["getPlanItemSchedule"]["path"],
  ): Promise<components["schemas"]["ScheduleResponse"] | null> {
    return this.request<components["schemas"]["ScheduleResponse"] | null>(
      "GET",
      `/plans/${encodeURIComponent(path.plan_id)}/items/${encodeURIComponent(path.item_id)}/schedule`,
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

  async getRegimen(
    path: operations["getRegimen"]["path"],
  ): Promise<components["schemas"]["RegimenResponse"]> {
    return this.request<components["schemas"]["RegimenResponse"]>(
      "GET",
      `/regimens/${encodeURIComponent(path.regimen_id)}`,
      undefined,
      undefined,
    );
  }

  async getRegimenSchedule(
    path: operations["getRegimenSchedule"]["path"],
  ): Promise<components["schemas"]["ScheduleResponse"] | null> {
    return this.request<components["schemas"]["ScheduleResponse"] | null>(
      "GET",
      `/regimens/${encodeURIComponent(path.regimen_id)}/schedule`,
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

  async getTracker(
    path: operations["getTracker"]["path"],
  ): Promise<components["schemas"]["TrackerResponse"]> {
    return this.request<components["schemas"]["TrackerResponse"]>(
      "GET",
      `/trackers/${encodeURIComponent(path.tracker_id)}`,
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

  async listActionProposalHistory(
    path: operations["listActionProposalHistory"]["path"],
    query?: operations["listActionProposalHistory"]["query"],
  ): Promise<components["schemas"]["ProposalHistoryResponse"]> {
    return this.request<components["schemas"]["ProposalHistoryResponse"]>(
      "GET",
      `/action-proposals/${encodeURIComponent(path.proposal_id)}/history`,
      query,
      undefined,
    );
  }

  async listActionProposals(
    query?: operations["listActionProposals"]["query"],
  ): Promise<components["schemas"]["ProposalListResponse"]> {
    return this.request<components["schemas"]["ProposalListResponse"]>(
      "GET",
      `/action-proposals`,
      query,
      undefined,
    );
  }

  async listContextHistory(
    path: operations["listContextHistory"]["path"],
    query?: operations["listContextHistory"]["query"],
  ): Promise<components["schemas"]["PlanningHistoryResponse"]> {
    return this.request<components["schemas"]["PlanningHistoryResponse"]>(
      "GET",
      `/contexts/${encodeURIComponent(path.context_id)}/history`,
      query,
      undefined,
    );
  }

  async listContexts(
    query?: operations["listContexts"]["query"],
  ): Promise<components["schemas"]["PlanningListResponse"]> {
    return this.request<components["schemas"]["PlanningListResponse"]>(
      "GET",
      `/contexts`,
      query,
      undefined,
    );
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

  async listGoalHistory(
    path: operations["listGoalHistory"]["path"],
    query?: operations["listGoalHistory"]["query"],
  ): Promise<components["schemas"]["PlanningHistoryResponse"]> {
    return this.request<components["schemas"]["PlanningHistoryResponse"]>(
      "GET",
      `/goals/${encodeURIComponent(path.goal_id)}/history`,
      query,
      undefined,
    );
  }

  async listGoals(
    query?: operations["listGoals"]["query"],
  ): Promise<components["schemas"]["PlanningListResponse"]> {
    return this.request<components["schemas"]["PlanningListResponse"]>(
      "GET",
      `/goals`,
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

  async listPlanHistory(
    path: operations["listPlanHistory"]["path"],
    query?: operations["listPlanHistory"]["query"],
  ): Promise<components["schemas"]["PlanningHistoryResponse"]> {
    return this.request<components["schemas"]["PlanningHistoryResponse"]>(
      "GET",
      `/plans/${encodeURIComponent(path.plan_id)}/history`,
      query,
      undefined,
    );
  }

  async listPlanOccurrenceHistory(
    path: operations["listPlanOccurrenceHistory"]["path"],
    query?: operations["listPlanOccurrenceHistory"]["query"],
  ): Promise<components["schemas"]["OccurrenceHistoryResponse"]> {
    return this.request<components["schemas"]["OccurrenceHistoryResponse"]>(
      "GET",
      `/plan-occurrences/${encodeURIComponent(path.occurrence_key)}/history`,
      query,
      undefined,
    );
  }

  async listPlanOccurrences(
    path: operations["listPlanOccurrences"]["path"],
    query: operations["listPlanOccurrences"]["query"],
  ): Promise<components["schemas"]["OccurrenceListResponse"]> {
    return this.request<components["schemas"]["OccurrenceListResponse"]>(
      "GET",
      `/plans/${encodeURIComponent(path.plan_id)}/occurrences`,
      query,
      undefined,
    );
  }

  async listPlans(
    query?: operations["listPlans"]["query"],
  ): Promise<components["schemas"]["PlanningListResponse"]> {
    return this.request<components["schemas"]["PlanningListResponse"]>(
      "GET",
      `/plans`,
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

  async listRegimenHistory(
    path: operations["listRegimenHistory"]["path"],
    query?: operations["listRegimenHistory"]["query"],
  ): Promise<components["schemas"]["PlanningHistoryResponse"]> {
    return this.request<components["schemas"]["PlanningHistoryResponse"]>(
      "GET",
      `/regimens/${encodeURIComponent(path.regimen_id)}/history`,
      query,
      undefined,
    );
  }

  async listRegimenOccurrences(
    path: operations["listRegimenOccurrences"]["path"],
    query: operations["listRegimenOccurrences"]["query"],
  ): Promise<components["schemas"]["OccurrenceListResponse"]> {
    return this.request<components["schemas"]["OccurrenceListResponse"]>(
      "GET",
      `/regimens/${encodeURIComponent(path.regimen_id)}/occurrences`,
      query,
      undefined,
    );
  }

  async listRegimens(
    query?: operations["listRegimens"]["query"],
  ): Promise<components["schemas"]["PlanningListResponse"]> {
    return this.request<components["schemas"]["PlanningListResponse"]>(
      "GET",
      `/regimens`,
      query,
      undefined,
    );
  }

  async listTrackerHistory(
    path: operations["listTrackerHistory"]["path"],
    query?: operations["listTrackerHistory"]["query"],
  ): Promise<components["schemas"]["PlanningHistoryResponse"]> {
    return this.request<components["schemas"]["PlanningHistoryResponse"]>(
      "GET",
      `/trackers/${encodeURIComponent(path.tracker_id)}/history`,
      query,
      undefined,
    );
  }

  async listTrackers(
    query?: operations["listTrackers"]["query"],
  ): Promise<components["schemas"]["PlanningListResponse"]> {
    return this.request<components["schemas"]["PlanningListResponse"]>(
      "GET",
      `/trackers`,
      query,
      undefined,
    );
  }

  async listTrackerVersions(
    path: operations["listTrackerVersions"]["path"],
    query?: operations["listTrackerVersions"]["query"],
  ): Promise<components["schemas"]["TrackerSchemaVersionListResponse"]> {
    return this.request<
      components["schemas"]["TrackerSchemaVersionListResponse"]
    >(
      "GET",
      `/trackers/${encodeURIComponent(path.tracker_id)}/versions`,
      query,
      undefined,
    );
  }

  async previewAIContext(
    requestBody: operations["previewAIContext"]["requestBody"],
  ): Promise<components["schemas"]["AIContextPack"]> {
    return this.request<components["schemas"]["AIContextPack"]>(
      "POST",
      `/ai/context`,
      undefined,
      requestBody,
    );
  }

  async rejectActionProposal(
    path: operations["rejectActionProposal"]["path"],
    requestBody: operations["rejectActionProposal"]["requestBody"],
  ): Promise<components["schemas"]["ProposalState"]> {
    return this.request<components["schemas"]["ProposalState"]>(
      "POST",
      `/action-proposals/${encodeURIComponent(path.proposal_id)}/reject`,
      undefined,
      requestBody,
    );
  }

  async reorderPlanItems(
    path: operations["reorderPlanItems"]["path"],
    requestBody: operations["reorderPlanItems"]["requestBody"],
  ): Promise<components["schemas"]["PlanResponse"]> {
    return this.request<components["schemas"]["PlanResponse"]>(
      "PUT",
      `/plans/${encodeURIComponent(path.plan_id)}/items/order`,
      undefined,
      requestBody,
    );
  }

  async searchAIEligibleHealthData(
    query: operations["searchAIEligibleHealthData"]["query"],
  ): Promise<components["schemas"]["AISearchResponse"]> {
    return this.request<components["schemas"]["AISearchResponse"]>(
      "GET",
      `/search`,
      query,
      undefined,
    );
  }

  async sendAssistantMessage(
    requestBody: operations["sendAssistantMessage"]["requestBody"],
  ): Promise<components["schemas"]["AssistantMessageResponse"]> {
    return this.request<components["schemas"]["AssistantMessageResponse"]>(
      "POST",
      `/assistant/messages`,
      undefined,
      requestBody,
    );
  }

  async transitionContext(
    path: operations["transitionContext"]["path"],
    requestBody: operations["transitionContext"]["requestBody"],
  ): Promise<components["schemas"]["ContextResponse"]> {
    return this.request<components["schemas"]["ContextResponse"]>(
      "PATCH",
      `/contexts/${encodeURIComponent(path.context_id)}/lifecycle`,
      undefined,
      requestBody,
    );
  }

  async transitionGoal(
    path: operations["transitionGoal"]["path"],
    requestBody: operations["transitionGoal"]["requestBody"],
  ): Promise<components["schemas"]["GoalResponse"]> {
    return this.request<components["schemas"]["GoalResponse"]>(
      "PATCH",
      `/goals/${encodeURIComponent(path.goal_id)}/lifecycle`,
      undefined,
      requestBody,
    );
  }

  async transitionPlan(
    path: operations["transitionPlan"]["path"],
    requestBody: operations["transitionPlan"]["requestBody"],
  ): Promise<components["schemas"]["PlanResponse"]> {
    return this.request<components["schemas"]["PlanResponse"]>(
      "PATCH",
      `/plans/${encodeURIComponent(path.plan_id)}/lifecycle`,
      undefined,
      requestBody,
    );
  }

  async transitionRegimen(
    path: operations["transitionRegimen"]["path"],
    requestBody: operations["transitionRegimen"]["requestBody"],
  ): Promise<components["schemas"]["RegimenResponse"]> {
    return this.request<components["schemas"]["RegimenResponse"]>(
      "PATCH",
      `/regimens/${encodeURIComponent(path.regimen_id)}/lifecycle`,
      undefined,
      requestBody,
    );
  }

  async updateContext(
    path: operations["updateContext"]["path"],
    requestBody: operations["updateContext"]["requestBody"],
  ): Promise<components["schemas"]["ContextResponse"]> {
    return this.request<components["schemas"]["ContextResponse"]>(
      "PATCH",
      `/contexts/${encodeURIComponent(path.context_id)}`,
      undefined,
      requestBody,
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

  async updateGoal(
    path: operations["updateGoal"]["path"],
    requestBody: operations["updateGoal"]["requestBody"],
  ): Promise<components["schemas"]["GoalResponse"]> {
    return this.request<components["schemas"]["GoalResponse"]>(
      "PATCH",
      `/goals/${encodeURIComponent(path.goal_id)}`,
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

  async updatePlan(
    path: operations["updatePlan"]["path"],
    requestBody: operations["updatePlan"]["requestBody"],
  ): Promise<components["schemas"]["PlanResponse"]> {
    return this.request<components["schemas"]["PlanResponse"]>(
      "PATCH",
      `/plans/${encodeURIComponent(path.plan_id)}`,
      undefined,
      requestBody,
    );
  }

  async updatePlanOccurrence(
    path: operations["updatePlanOccurrence"]["path"],
    requestBody: operations["updatePlanOccurrence"]["requestBody"],
  ): Promise<components["schemas"]["OccurrenceActionResponse"]> {
    return this.request<components["schemas"]["OccurrenceActionResponse"]>(
      "PATCH",
      `/plan-occurrences/${encodeURIComponent(path.occurrence_key)}`,
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

  async updateRegimen(
    path: operations["updateRegimen"]["path"],
    requestBody: operations["updateRegimen"]["requestBody"],
  ): Promise<components["schemas"]["RegimenResponse"]> {
    return this.request<components["schemas"]["RegimenResponse"]>(
      "PATCH",
      `/regimens/${encodeURIComponent(path.regimen_id)}`,
      undefined,
      requestBody,
    );
  }

  async updateTracker(
    path: operations["updateTracker"]["path"],
    requestBody: operations["updateTracker"]["requestBody"],
  ): Promise<components["schemas"]["TrackerResponse"]> {
    return this.request<components["schemas"]["TrackerResponse"]>(
      "PATCH",
      `/trackers/${encodeURIComponent(path.tracker_id)}`,
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
    const payload = await response.json().catch((error: unknown) => {
      if (error instanceof SyntaxError) return undefined;
      throw error;
    });
    if (!response.ok)
      throw new ApiError(
        response.status,
        payload as components["schemas"]["ErrorResponse"] | undefined,
      );
    return payload as T;
  }
}

export { HealthApiClient as ProfileApiClient };
