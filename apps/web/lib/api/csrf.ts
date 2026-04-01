"use client";

import { CSRF_TOKEN_COOKIE_NAME, normalizeCookieToken } from "./access-token";

function readBrowserCookie(name: string): string | null {
  if (typeof document === "undefined") {
    return null;
  }

  const prefix = `${encodeURIComponent(name)}=`;
  const cookie = document.cookie
    .split("; ")
    .find((item) => item.startsWith(prefix));

  if (!cookie) {
    return null;
  }

  return normalizeCookieToken(decodeURIComponent(cookie.slice(prefix.length)));
}

export function getBrowserCsrfHeaders(): HeadersInit | undefined {
  const csrfToken = readBrowserCookie(CSRF_TOKEN_COOKIE_NAME);
  if (!csrfToken) {
    return undefined;
  }

  return {
    "X-CSRF-Token": csrfToken
  };
}
