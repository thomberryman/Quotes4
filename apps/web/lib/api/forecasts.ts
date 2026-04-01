import { getServerApiClient } from "./server-client";

export async function getForecastPolicy() {
  const api = await getServerApiClient();
  return api.getForecastPolicy();
}

export async function getProjectForecast(projectId: string) {
  const api = await getServerApiClient();
  return api.getProjectForecast(projectId);
}
