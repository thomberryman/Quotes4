import type { DashboardQueryOptions } from "@quotes4/contracts";

import { getServerApiClient } from "./server-client";

export async function getOperationalDashboard(options?: DashboardQueryOptions) {
  const api = await getServerApiClient();
  return api.getOperationalDashboard(options);
}

export async function listJobs() {
  const api = await getServerApiClient();
  return api.listJobs();
}
