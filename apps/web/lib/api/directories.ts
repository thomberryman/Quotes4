import { getServerApiClient } from "./server-client";

export async function listClients() {
  const api = await getServerApiClient();
  return api.listClients();
}

export async function listContacts() {
  const api = await getServerApiClient();
  return api.listContacts();
}

export async function listDisciplines() {
  const api = await getServerApiClient();
  return api.listDisciplines();
}
