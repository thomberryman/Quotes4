import { getServerApiClient } from "./server-client";

export async function listQuotes(projectId?: string) {
  const api = await getServerApiClient();
  return api.listQuotes(projectId ? { projectId } : undefined);
}

export async function getQuote(quoteId: string) {
  const api = await getServerApiClient();
  return api.getQuote(quoteId);
}

export async function listQuoteVersions(quoteId: string) {
  const api = await getServerApiClient();
  return api.listQuoteVersions(quoteId);
}

export async function getQuoteVersion(versionId: string) {
  const api = await getServerApiClient();
  return api.getQuoteVersion(versionId);
}
