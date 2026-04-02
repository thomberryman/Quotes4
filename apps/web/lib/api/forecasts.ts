import { getServerApiClient } from "./server-client";

export async function getForecastPolicy() {
  const api = await getServerApiClient();
  return api.getForecastPolicy();
}

export async function getProjectForecast(projectId: string) {
  const api = await getServerApiClient();
  return api.getProjectForecast(projectId);
}

export async function getForecastPhasingWorkspace(options?: {
  fromMonth?: string;
  toMonth?: string;
  clientId?: string;
  projectId?: string;
  disciplineId?: string;
  status?: string;
  scenarioKey?: string;
  rowMode?: string;
}) {
  const api = await getServerApiClient();
  return api.getForecastPhasingWorkspace(options);
}
