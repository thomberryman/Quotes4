"use client";

import { createApiClient } from "@quotes4/contracts";

import { getBrowserApiBaseUrl } from "./config";
import { getBrowserCsrfHeaders } from "./csrf";

export function getBrowserApiClient() {
  return createApiClient({
    baseUrl: getBrowserApiBaseUrl(),
    defaultInit: {
      credentials: "include"
    },
    getHeaders: getBrowserCsrfHeaders
  });
}
