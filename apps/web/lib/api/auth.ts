import type { LoginRequest } from "@quotes4/contracts";

import { getBrowserApiClient } from "./browser-client";

export async function createBrowserSession(payload: LoginRequest) {
  const api = getBrowserApiClient();
  return api.createSession(payload);
}

export async function destroyBrowserSession() {
  const api = getBrowserApiClient();
  await api.destroySession();
}
