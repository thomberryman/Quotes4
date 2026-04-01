import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { ACCESS_TOKEN_COOKIE_NAME } from "@/lib/api/access-token";

export default async function HomePage() {
  const cookieStore = await cookies();
  redirect(cookieStore.get(ACCESS_TOKEN_COOKIE_NAME) ? "/dashboard" : "/login");
}
