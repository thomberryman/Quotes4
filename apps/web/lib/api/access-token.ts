export const ACCESS_TOKEN_COOKIE_NAME =
  process.env.NEXT_PUBLIC_AUTH_ACCESS_COOKIE_NAME?.trim() || "quotes4_access_token";
export const CSRF_TOKEN_COOKIE_NAME =
  process.env.NEXT_PUBLIC_AUTH_CSRF_COOKIE_NAME?.trim() || "quotes4_csrf_token";

export function normalizeCookieToken(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }

  if (value.length >= 2 && value.startsWith("\"") && value.endsWith("\"")) {
    return value.slice(1, -1);
  }

  return value;
}
