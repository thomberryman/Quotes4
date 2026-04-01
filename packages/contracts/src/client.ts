import type {
  ActualsImportBatchDetailRead,
  ActualsImportBatchListResponse,
  ActualsImportRowListResponse,
  ApiProblem,
  ApproveActualsImportBatchRequest,
  ApproveActualsImportBatchResponse,
  ApproveQuoteIngestionRunRequest,
  AuditEventListResponse,
  ComparableSelectionUpdateRequest,
  ComparableSelectionUpdateResponse,
  ContactListResponse,
  CounterpartyListResponse,
  CreateActualsImportBatchRequest,
  CreateQuoteIngestionRunRequest,
  CreateQuoteIngestionUploadRequest,
  DashboardDrilldownResponse,
  DisciplineListResponse,
  FinalizeUploadRequest,
  FinalizeUploadResponse,
  FinalizeQuoteIngestionUploadRequest,
  FinalizeQuoteIngestionUploadResponse,
  ForecastDetailRead,
  ForecastLineAllocationsReplaceRequest,
  ForecastPolicySummary,
  ForecastRecalculateResponse,
  ForecastVersionCreateRequest,
  ForecastVersionRead,
  ForecastVersionUpdateRequest,
  HealthResponse,
  InvitationRequest,
  InvitationResponse,
  JobListResponse,
  JobRecord,
  LoginRequest,
  LogoutResponse,
  OperationalDashboardResponse,
  PresignUploadRequest,
  PresignUploadResponse,
  ProcessActualsBatchResponse,
  PredictionOverridesPatchRequest,
  PredictionRunCreateRequest,
  PredictionRunDetailRead,
  PredictionRunListResponse,
  PredictionScenarioPromotionResponse,
  PredictionScenarioPromoteRequest,
  PredictionScenarioUpdateRequest,
  ProjectActualsVsQuoteRead,
  ProjectComparablesResponse,
  ProjectCreateRequest,
  ProjectMetadataPutRequest,
  ProjectPredictiveGuidanceResponse,
  ProjectListResponse,
  ProjectRead,
  ProjectRecommendationsResponse,
  ProjectUpdateRequest,
  QuoteApprovalResponse,
  QuoteIngestionRunDetail,
  QuoteIngestionRunListResponse,
  QuoteIngestionUploadIntentResponse,
  QuoteParsePreviewResponse,
  QuoteCreateRequest,
  QuoteListResponse,
  QuoteRead,
  RejectActualsImportBatchRequest,
  RejectActualsImportBatchResponse,
  RejectQuoteIngestionRunRequest,
  RerunQuoteIngestionRunRequest,
  QuoteUpdateRequest,
  QuoteVersionCreateRequest,
  QuoteVersionRead,
  QuoteVersionSummary,
  QuoteVersionUpdateRequest,
  SessionResponse,
  UpdateActualsImportRowDecisionRequest,
  UpdateQuoteIngestionReviewRequest,
  UserSummary,
} from "./generated/api-types";

export class ApiClientError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly problem: ApiProblem | null,
  ) {
    super(message);
    this.name = "ApiClientError";
  }
}

export interface ApiClientConfig {
  baseUrl: string;
  defaultInit?: RequestInit;
  getAccessToken?: () => string | null | undefined;
  getHeaders?:
    | (() => HeadersInit | null | undefined)
    | (() => Promise<HeadersInit | null | undefined>);
}

export interface DashboardQueryOptions {
  fromMonth?: string;
  toMonth?: string;
  clientId?: string;
  projectId?: string;
  disciplineId?: string;
  status?: string;
}

export interface AuditEventsQueryOptions {
  projectId?: string;
  entityType?: string;
  entityId?: string;
  limit?: number;
}

export interface ActualsImportRowsQueryOptions {
  reviewQueue?: string;
}

export interface QuoteListQueryOptions {
  projectId?: string;
}

export interface JobListQueryOptions {
  status?: string;
  queueName?: string;
  relatedEntityType?: string;
  relatedEntityId?: string;
  limit?: number;
}

function isApiProblem(value: unknown): value is ApiProblem {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.title === "string" &&
    typeof candidate.detail === "string" &&
    typeof candidate.status === "number" &&
    typeof candidate.requestId === "string"
  );
}

function joinUrl(baseUrl: string, path: string): string {
  return `${baseUrl.replace(/\/$/, "")}${path}`;
}

function withQuery(
  path: string,
  query: Record<string, string | number | boolean | undefined>,
) {
  const search = new URLSearchParams();

  Object.entries(query).forEach(([key, value]) => {
    if (value === undefined) {
      return;
    }

    search.set(key, String(value));
  });

  const queryString = search.toString();
  return queryString ? `${path}?${queryString}` : path;
}

export function createApiClient(config: ApiClientConfig) {
  async function buildHeaders(init?: RequestInit): Promise<Headers> {
    const headers = new Headers(config.defaultInit?.headers ?? {});

    const dynamicHeaders = await config.getHeaders?.();
    if (dynamicHeaders) {
      new Headers(dynamicHeaders).forEach((value, key) => {
        headers.set(key, value);
      });
    }

    if (init?.headers) {
      new Headers(init.headers).forEach((value, key) => {
        headers.set(key, value);
      });
    }

    if (init?.body && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }

    const accessToken = config.getAccessToken?.();
    if (accessToken && !headers.has("Authorization")) {
      headers.set("Authorization", `Bearer ${accessToken}`);
    }

    return headers;
  }

  async function request<T>(path: string, init?: RequestInit): Promise<T> {
    const headers = await buildHeaders(init);
    if (!headers.has("Accept")) {
      headers.set("Accept", "application/json");
    }

    const response = await fetch(joinUrl(config.baseUrl, path), {
      ...config.defaultInit,
      ...init,
      headers,
    });

    if (!response.ok) {
      let problem: ApiProblem | null = null;

      try {
        const json = (await response.json()) as unknown;
        problem = isApiProblem(json) ? json : null;
      } catch {
        problem = null;
      }

      throw new ApiClientError(
        problem?.detail ?? "API request failed.",
        response.status,
        problem,
      );
    }

    if (response.status === 204) {
      return undefined as T;
    }

    return (await response.json()) as T;
  }

  async function requestText(
    path: string,
    init?: RequestInit,
  ): Promise<string> {
    const headers = await buildHeaders(init);

    const response = await fetch(joinUrl(config.baseUrl, path), {
      ...config.defaultInit,
      ...init,
      headers,
    });

    if (!response.ok) {
      let problem: ApiProblem | null = null;

      try {
        const json = (await response.json()) as unknown;
        problem = isApiProblem(json) ? json : null;
      } catch {
        problem = null;
      }

      throw new ApiClientError(
        problem?.detail ?? "API request failed.",
        response.status,
        problem,
      );
    }

    return await response.text();
  }

  function dashboardQuery(options?: DashboardQueryOptions) {
    return {
      fromMonth: options?.fromMonth,
      toMonth: options?.toMonth,
      clientId: options?.clientId,
      projectId: options?.projectId,
      disciplineId: options?.disciplineId,
      status: options?.status,
    };
  }

  function auditQuery(options?: AuditEventsQueryOptions) {
    return {
      projectId: options?.projectId,
      entityType: options?.entityType,
      entityId: options?.entityId,
      limit: options?.limit,
    };
  }

  function actualsImportRowsQuery(options?: ActualsImportRowsQueryOptions) {
    return {
      reviewQueue: options?.reviewQueue,
    };
  }

  function quoteListQuery(options?: QuoteListQueryOptions) {
    return {
      projectId: options?.projectId,
    };
  }

  function jobListQuery(options?: JobListQueryOptions) {
    return {
      status: options?.status,
      queueName: options?.queueName,
      relatedEntityType: options?.relatedEntityType,
      relatedEntityId: options?.relatedEntityId,
      limit: options?.limit,
    };
  }

  return {
    getHealth: () => request<HealthResponse>("/api/v1/health"),
    getCurrentUser: () => request<UserSummary>("/api/v1/auth/me"),
    listAuditEvents: (options?: AuditEventsQueryOptions) =>
      request<AuditEventListResponse>(
        withQuery("/api/v1/audit/events", auditQuery(options)),
      ),
    getOperationalDashboard: (options?: DashboardQueryOptions) =>
      request<OperationalDashboardResponse>(
        withQuery("/api/v1/dashboards/operational", dashboardQuery(options)),
      ),
    getDashboardDrilldown: (view: string, options?: DashboardQueryOptions) =>
      request<DashboardDrilldownResponse>(
        withQuery(
          `/api/v1/dashboards/drilldowns/${view}`,
          dashboardQuery(options),
        ),
      ),
    exportDashboardDrilldownCsv: (
      view: string,
      options?: DashboardQueryOptions,
    ) =>
      requestText(
        withQuery(
          `/api/v1/dashboards/drilldowns/${view}/csv`,
          dashboardQuery(options),
        ),
        {
          headers: {
            Accept: "text/csv",
          },
        },
      ),
    createInvitation: (payload: InvitationRequest) =>
      request<InvitationResponse>("/api/v1/auth/invitations", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    createSession: (payload: LoginRequest) =>
      request<SessionResponse>("/api/v1/auth/session", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    destroySession: () =>
      request<LogoutResponse>("/api/v1/auth/session", {
        method: "DELETE",
      }),
    listClients: () => request<CounterpartyListResponse>("/api/v1/clients"),
    listContacts: () => request<ContactListResponse>("/api/v1/contacts"),
    listProjects: () => request<ProjectListResponse>("/api/v1/projects"),
    createProject: (payload: ProjectCreateRequest) =>
      request<ProjectRead>("/api/v1/projects", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    listDisciplines: () =>
      request<DisciplineListResponse>("/api/v1/disciplines"),
    getProject: (projectId: string) =>
      request<ProjectRead>(`/api/v1/projects/${projectId}`),
    updateProject: (projectId: string, payload: ProjectUpdateRequest) =>
      request<ProjectRead>(`/api/v1/projects/${projectId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    putProjectMetadata: (
      projectId: string,
      payload: ProjectMetadataPutRequest,
    ) =>
      request<ProjectRead>(`/api/v1/projects/${projectId}/metadata`, {
        method: "PUT",
        body: JSON.stringify(payload),
      }),
    getProjectActualsVsQuote: (projectId: string) =>
      request<ProjectActualsVsQuoteRead>(
        `/api/v1/projects/${projectId}/actuals-vs-quote`,
      ),
    getProjectPredictiveGuidance: (
      projectId: string,
      options?: {
        quoteVersionId?: string;
        limit?: number;
        disciplineId?: string;
      },
    ) =>
      request<ProjectPredictiveGuidanceResponse>(
        withQuery(`/api/v1/projects/${projectId}/predictive-guidance`, {
          quoteVersionId: options?.quoteVersionId,
          limit: options?.limit,
          disciplineId: options?.disciplineId,
        }),
      ),
    createPredictionRun: (
      projectId: string,
      payload: PredictionRunCreateRequest,
    ) =>
      request<PredictionRunDetailRead>(
        `/api/v1/projects/${projectId}/prediction-runs`,
        {
          method: "POST",
          body: JSON.stringify(payload),
        },
      ),
    listPredictionRuns: (projectId: string) =>
      request<PredictionRunListResponse>(
        `/api/v1/projects/${projectId}/prediction-runs`,
      ),
    getPredictionRun: (projectId: string, runId: string) =>
      request<PredictionRunDetailRead>(
        `/api/v1/projects/${projectId}/prediction-runs/${runId}`,
      ),
    patchPredictionOverrides: (
      projectId: string,
      runId: string,
      payload: PredictionOverridesPatchRequest,
    ) =>
      request<PredictionRunDetailRead>(
        `/api/v1/projects/${projectId}/prediction-runs/${runId}/overrides`,
        {
          method: "PATCH",
          body: JSON.stringify(payload),
        },
      ),
    updatePredictionScenario: (
      projectId: string,
      runId: string,
      scenarioKey: string,
      payload: PredictionScenarioUpdateRequest,
    ) =>
      request<PredictionRunDetailRead>(
        `/api/v1/projects/${projectId}/prediction-runs/${runId}/scenarios/${scenarioKey}`,
        {
          method: "PATCH",
          body: JSON.stringify(payload),
        },
      ),
    promotePredictionScenario: (
      projectId: string,
      runId: string,
      payload: PredictionScenarioPromoteRequest,
    ) =>
      request<PredictionScenarioPromotionResponse>(
        `/api/v1/projects/${projectId}/prediction-runs/${runId}/promote-scenario`,
        {
          method: "POST",
          body: JSON.stringify(payload),
        },
      ),
    listQuotes: (options?: QuoteListQueryOptions) =>
      request<QuoteListResponse>(
        withQuery("/api/v1/quotes", quoteListQuery(options)),
      ),
    createQuote: (payload: QuoteCreateRequest) =>
      request<QuoteRead>("/api/v1/quotes", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    getQuote: (quoteId: string) =>
      request<QuoteRead>(`/api/v1/quotes/${quoteId}`),
    updateQuote: (quoteId: string, payload: QuoteUpdateRequest) =>
      request<QuoteRead>(`/api/v1/quotes/${quoteId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    listQuoteVersions: (quoteId: string) =>
      request<QuoteVersionSummary[]>(`/api/v1/quotes/${quoteId}/versions`),
    createQuoteVersion: (quoteId: string, payload: QuoteVersionCreateRequest) =>
      request<QuoteVersionRead>(`/api/v1/quotes/${quoteId}/versions`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    getQuoteVersion: (versionId: string) =>
      request<QuoteVersionRead>(`/api/v1/quotes/versions/${versionId}`),
    updateQuoteVersion: (
      versionId: string,
      payload: QuoteVersionUpdateRequest,
    ) =>
      request<QuoteVersionRead>(`/api/v1/quotes/versions/${versionId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    issueQuoteVersion: (versionId: string) =>
      request<QuoteVersionRead>(`/api/v1/quotes/versions/${versionId}/issue`, {
        method: "POST",
      }),
    createUploadIntent: (payload: PresignUploadRequest) =>
      request<PresignUploadResponse>("/api/v1/files/uploads/presign", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    finalizeUpload: (payload: FinalizeUploadRequest) =>
      request<FinalizeUploadResponse>("/api/v1/files/uploads/finalize", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    listActualsImportBatches: () =>
      request<ActualsImportBatchListResponse>(
        "/api/v1/actuals-imports/batches",
      ),
    createActualsImportBatch: (payload: CreateActualsImportBatchRequest) =>
      request<ActualsImportBatchDetailRead>("/api/v1/actuals-imports/batches", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    getActualsImportBatch: (batchId: string) =>
      request<ActualsImportBatchDetailRead>(
        `/api/v1/actuals-imports/batches/${batchId}`,
      ),
    listActualsImportRows: (
      batchId: string,
      options?: ActualsImportRowsQueryOptions,
    ) =>
      request<ActualsImportRowListResponse>(
        withQuery(
          `/api/v1/actuals-imports/batches/${batchId}/rows`,
          actualsImportRowsQuery(options),
        ),
      ),
    processActualsImportBatch: (batchId: string) =>
      request<ProcessActualsBatchResponse>(
        `/api/v1/actuals-imports/batches/${batchId}/process`,
        {
          method: "POST",
        },
      ),
    updateActualsImportRowDecision: (
      rowId: string,
      payload: UpdateActualsImportRowDecisionRequest,
    ) =>
      request<ActualsImportRowListResponse>(
        `/api/v1/actuals-imports/rows/${rowId}/decision`,
        {
          method: "PATCH",
          body: JSON.stringify(payload),
        },
      ),
    approveActualsImportBatch: (
      batchId: string,
      payload: ApproveActualsImportBatchRequest,
    ) =>
      request<ApproveActualsImportBatchResponse>(
        `/api/v1/actuals-imports/batches/${batchId}/approve`,
        {
          method: "POST",
          body: JSON.stringify(payload),
        },
      ),
    rejectActualsImportBatch: (
      batchId: string,
      payload: RejectActualsImportBatchRequest,
    ) =>
      request<RejectActualsImportBatchResponse>(
        `/api/v1/actuals-imports/batches/${batchId}/reject`,
        {
          method: "POST",
          body: JSON.stringify(payload),
        },
      ),
    createQuoteIngestionUploadIntent: (
      payload: CreateQuoteIngestionUploadRequest,
    ) =>
      request<QuoteIngestionUploadIntentResponse>(
        "/api/v1/quote-ingestion/uploads/presign",
        {
          method: "POST",
          body: JSON.stringify(payload),
        },
      ),
    finalizeQuoteIngestionUpload: (
      payload: FinalizeQuoteIngestionUploadRequest,
    ) =>
      request<FinalizeQuoteIngestionUploadResponse>(
        "/api/v1/quote-ingestion/uploads/finalize",
        {
          method: "POST",
          body: JSON.stringify(payload),
        },
      ),
    listQuoteIngestionRuns: () =>
      request<QuoteIngestionRunListResponse>("/api/v1/quote-ingestion/runs"),
    createQuoteIngestionRun: (payload: CreateQuoteIngestionRunRequest) =>
      request<QuoteIngestionRunDetail>("/api/v1/quote-ingestion/runs", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    getQuoteIngestionRun: (runId: string) =>
      request<QuoteIngestionRunDetail>(`/api/v1/quote-ingestion/runs/${runId}`),
    updateQuoteIngestionReview: (
      runId: string,
      payload: UpdateQuoteIngestionReviewRequest,
    ) =>
      request<QuoteIngestionRunDetail>(
        `/api/v1/quote-ingestion/runs/${runId}/review`,
        {
          method: "PATCH",
          body: JSON.stringify(payload),
        },
      ),
    approveQuoteIngestionRun: (
      runId: string,
      payload?: ApproveQuoteIngestionRunRequest,
    ) =>
      request<QuoteApprovalResponse>(
        `/api/v1/quote-ingestion/runs/${runId}/approve`,
        {
          method: "POST",
          body: JSON.stringify(payload ?? {}),
        },
      ),
    rerunQuoteIngestionRun: (
      runId: string,
      payload: RerunQuoteIngestionRunRequest,
    ) =>
      request<QuoteIngestionRunDetail>(
        `/api/v1/quote-ingestion/runs/${runId}/rerun`,
        {
          method: "POST",
          body: JSON.stringify(payload),
        },
      ),
    rejectQuoteIngestionRun: (
      runId: string,
      payload: RejectQuoteIngestionRunRequest,
    ) =>
      request<QuoteIngestionRunDetail>(
        `/api/v1/quote-ingestion/runs/${runId}/reject`,
        {
          method: "POST",
          body: JSON.stringify(payload),
        },
      ),
    previewQuoteParse: (objectKey: string) =>
      request<QuoteParsePreviewResponse>(
        withQuery("/api/v1/quote-ingestion/preview", { objectKey }),
      ),
    getForecastPolicy: () =>
      request<ForecastPolicySummary>("/api/v1/forecasts/policy"),
    getProjectForecast: (projectId: string) =>
      request<ForecastDetailRead>(`/api/v1/forecasts/projects/${projectId}`),
    getForecastVersion: (versionId: string) =>
      request<ForecastVersionRead>(`/api/v1/forecasts/versions/${versionId}`),
    createForecastVersion: (
      projectId: string,
      payload: ForecastVersionCreateRequest,
    ) =>
      request<ForecastVersionRead>(
        `/api/v1/forecasts/projects/${projectId}/versions`,
        {
          method: "POST",
          body: JSON.stringify(payload),
        },
      ),
    updateForecastVersion: (
      versionId: string,
      payload: ForecastVersionUpdateRequest,
    ) =>
      request<ForecastVersionRead>(`/api/v1/forecasts/versions/${versionId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    replaceForecastLineAllocations: (
      lineId: string,
      payload: ForecastLineAllocationsReplaceRequest,
    ) =>
      request<ForecastVersionRead>(
        `/api/v1/forecasts/lines/${lineId}/allocations`,
        {
          method: "PUT",
          body: JSON.stringify(payload),
        },
      ),
    submitForecastVersion: (versionId: string) =>
      request<ForecastVersionRead>(
        `/api/v1/forecasts/versions/${versionId}/submit`,
        {
          method: "POST",
        },
      ),
    lockForecastVersion: (versionId: string) =>
      request<ForecastVersionRead>(
        `/api/v1/forecasts/versions/${versionId}/lock`,
        {
          method: "POST",
        },
      ),
    recalculateForecast: (projectId: string) =>
      request<ForecastRecalculateResponse>(
        `/api/v1/forecasts/projects/${projectId}/recalculate`,
        {
          method: "POST",
        },
      ),
    getProjectComparables: (
      projectId: string,
      options?: {
        quoteVersionId?: string;
        limit?: number;
        disciplineId?: string;
        includePinned?: boolean;
      },
    ) =>
      request<ProjectComparablesResponse>(
        withQuery(`/api/v1/projects/${projectId}/comparables`, {
          quoteVersionId: options?.quoteVersionId,
          limit: options?.limit,
          disciplineId: options?.disciplineId,
          includePinned: options?.includePinned,
        }),
      ),
    getProjectRecommendations: (
      projectId: string,
      options?: {
        quoteVersionId?: string;
        limit?: number;
        disciplineId?: string;
      },
    ) =>
      request<ProjectRecommendationsResponse>(
        withQuery(`/api/v1/projects/${projectId}/recommendations`, {
          quoteVersionId: options?.quoteVersionId,
          limit: options?.limit,
          disciplineId: options?.disciplineId,
        }),
      ),
    updateProjectComparableSelection: (
      projectId: string,
      payload: ComparableSelectionUpdateRequest,
    ) =>
      request<ComparableSelectionUpdateResponse>(
        `/api/v1/projects/${projectId}/comparable-selection`,
        {
          method: "PUT",
          body: JSON.stringify(payload),
        },
      ),
    listJobs: (options?: JobListQueryOptions) =>
      request<JobListResponse>(withQuery("/api/v1/jobs", jobListQuery(options))),
    getJob: (jobId: string) => request<JobRecord>(`/api/v1/jobs/${jobId}`),
  };
}
