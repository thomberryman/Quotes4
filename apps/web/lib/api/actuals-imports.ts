import { getServerApiClient } from "./server-client";

export async function listActualsImportBatches() {
  const api = await getServerApiClient();
  return api.listActualsImportBatches();
}

export async function getActualsImportBatch(batchId: string) {
  const api = await getServerApiClient();
  return api.getActualsImportBatch(batchId);
}

export async function listActualsImportRows(
  batchId: string,
  reviewQueue?: string | null,
) {
  const api = await getServerApiClient();
  if (reviewQueue) {
    return api.listActualsImportRows(batchId, { reviewQueue });
  }
  return api.listActualsImportRows(batchId);
}
