import { getServerApiClient } from "./server-client";

export async function listProjects() {
  const api = await getServerApiClient();
  return api.listProjects();
}

export async function getProject(projectId: string) {
  const api = await getServerApiClient();
  return api.getProject(projectId);
}

export async function getProjectActualsVsQuote(projectId: string) {
  const api = await getServerApiClient();
  return api.getProjectActualsVsQuote(projectId);
}

export async function getProjectPredictiveGuidance(
  projectId: string,
  options?: {
    disciplineId?: string;
    limit?: number;
    quoteVersionId?: string;
  }
) {
  const api = await getServerApiClient();
  return api.getProjectPredictiveGuidance(projectId, {
    limit: options?.limit ?? 25,
    ...(options?.disciplineId ? { disciplineId: options.disciplineId } : {}),
    ...(options?.quoteVersionId ? { quoteVersionId: options.quoteVersionId } : {})
  });
}

export async function listPredictionRuns(projectId: string) {
  const api = await getServerApiClient();
  return api.listPredictionRuns(projectId);
}

export async function getPredictionRun(projectId: string, runId: string) {
  const api = await getServerApiClient();
  return api.getPredictionRun(projectId, runId);
}
