import { getServerApiClient } from "./server-client";

export async function listQuoteIngestionRuns() {
  const api = await getServerApiClient();
  return api.listQuoteIngestionRuns();
}

export async function getQuoteIngestionRun(runId: string) {
  const api = await getServerApiClient();
  return api.getQuoteIngestionRun(runId);
}
