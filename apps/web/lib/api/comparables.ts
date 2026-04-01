import { getServerApiClient } from "./server-client";

export async function getProjectComparables(
  projectId: string,
  options?: {
    disciplineId?: string;
    includePinned?: boolean;
    limit?: number;
    quoteVersionId?: string;
  }
) {
  const api = await getServerApiClient();
  return api.getProjectComparables(projectId, {
    includePinned: options?.includePinned ?? true,
    limit: options?.limit ?? 10,
    ...(options?.disciplineId ? { disciplineId: options.disciplineId } : {}),
    ...(options?.quoteVersionId ? { quoteVersionId: options.quoteVersionId } : {})
  });
}

export async function getProjectRecommendations(
  projectId: string,
  options?: {
    disciplineId?: string;
    limit?: number;
    quoteVersionId?: string;
  }
) {
  const api = await getServerApiClient();
  return api.getProjectRecommendations(projectId, {
    limit: options?.limit ?? 10,
    ...(options?.disciplineId ? { disciplineId: options.disciplineId } : {}),
    ...(options?.quoteVersionId ? { quoteVersionId: options.quoteVersionId } : {})
  });
}
