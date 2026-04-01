import { createApiClient } from "@quotes4/contracts";
import { cookies } from "next/headers";

import { ACCESS_TOKEN_COOKIE_NAME, normalizeCookieToken } from "./access-token";
import { getApiBaseUrl } from "./config";

export async function getServerApiClient() {
  const cookieStore = await cookies();
  const accessToken = normalizeCookieToken(
    cookieStore.get(ACCESS_TOKEN_COOKIE_NAME)?.value ?? null,
  );

  return createApiClient({
    baseUrl: getApiBaseUrl(),
    defaultInit: {
      cache: "no-store",
      credentials: "include"
    },
    getAccessToken: () => accessToken
  });
}

export async function getServerAccessToken(): Promise<string | null> {
  const cookieStore = await cookies();
  return normalizeCookieToken(cookieStore.get(ACCESS_TOKEN_COOKIE_NAME)?.value ?? null);
}
