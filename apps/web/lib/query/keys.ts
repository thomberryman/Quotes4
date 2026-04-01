export const queryKeys = {
  currentUser: ["current-user"] as const,
  operationalDashboard: (filtersKey: string) =>
    ["operational-dashboard", filtersKey] as const,
  dashboardDrilldown: (view: string, filtersKey: string) =>
    ["dashboard-drilldown", view, filtersKey] as const,
  jobs: ["jobs"] as const,
  auditEvents: (projectId: string) => ["audit-events", projectId] as const,
  clients: ["clients"] as const,
  contacts: ["contacts"] as const,
  projects: ["projects"] as const,
  project: (projectId: string) => ["project", projectId] as const,
  quotes: ["quotes"] as const,
  quote: (quoteId: string) => ["quote", quoteId] as const,
  quoteVersions: (quoteId: string) => ["quote-versions", quoteId] as const,
  quoteVersion: (versionId: string) => ["quote-version", versionId] as const,
  quoteIngestionRuns: ["quote-ingestion-runs"] as const,
  quoteIngestionRun: (runId: string) => ["quote-ingestion-run", runId] as const,
  forecastPolicy: ["forecast-policy"] as const,
  projectForecast: (projectId: string) =>
    ["project-forecast", projectId] as const,
  forecastVersion: (versionId: string) =>
    ["forecast-version", versionId] as const,
  projectComparables: (
    projectId: string,
    options?: {
      disciplineId?: string;
      includePinned?: boolean;
    },
  ) =>
    [
      "project-comparables",
      projectId,
      options?.disciplineId ?? "all",
      options?.includePinned ?? true,
    ] as const,
  projectRecommendations: (
    projectId: string,
    options?: {
      disciplineId?: string;
    },
  ) =>
    ["project-recommendations", projectId, options?.disciplineId ?? "all"] as const,
  projectPredictiveGuidance: (
    projectId: string,
    options?: {
      disciplineId?: string;
    },
  ) =>
    [
      "project-predictive-guidance",
      projectId,
      options?.disciplineId ?? "all",
    ] as const,
  predictionRuns: (projectId: string) =>
    ["prediction-runs", projectId] as const,
  predictionRun: (projectId: string, runId: string) =>
    ["prediction-run", projectId, runId] as const,
  actualsImportBatches: ["actuals-import-batches"] as const,
  actualsImportBatch: (batchId: string) =>
    ["actuals-import-batch", batchId] as const,
  actualsImportRows: (batchId: string, reviewQueue: string | null) =>
    ["actuals-import-rows", batchId, reviewQueue ?? "all"] as const,
};
